from fontTools.misc.py23 import *
import fontTools
from fontTools.feaLib.ast import *
from collections import OrderedDict
from fontTools.misc.xmlWriter import XMLWriter

class GTableUnparser:
    def __init__(self, table, ff, languageSystems, font=None):
        self.table = table.table
        self.font = font
        self.feature = ff
        self.lookupNames = []
        self.index = 0
        self.lookups = {}
        self.sharedClasses = {}
        self.languageSystems = languageSystems
        self.sharedLookups = set([])

    def gensym(self):
        self.index = self.index + 1
        return str(self.index)

    def makeGlyphClass(self, glyphnames):
        if len(glyphnames) == 1: return GlyphName(glyphnames[0])
        asclass = GlyphClass([GlyphName(x) for x in glyphnames])
        if len(glyphnames) < 10:
            return asclass
        # Share it
        if not tuple(glyphnames) in self.sharedClasses:
            self.sharedClasses[tuple(sorted(glyphnames))] = GlyphClassDefinition("GlyphClass"+self.gensym(), asclass)
        return GlyphClassName(self.sharedClasses[tuple(sorted(glyphnames))])

    def unparse(self, doLookups = True):
        if doLookups:
            self.unparseLookups()
        self.collectFeatures()
        self.tidyFeatures()
        if doLookups:
            self.inlineFeatures()
            self.addGlyphClasses()
        self.addFeatures(doLookups=doLookups)

    def addGlyphClasses(self):
        self.feature.statements.append(Comment('\n# Glyph classes\n'))
        for gc in self.sharedClasses.values():
            self.feature.statements.append(gc)

    def _prepareFeatureLangSys(self, langTag, langSys, table, features, scriptTag):
        # This is a part of prepareFeatures
        for featureIdx in langSys.FeatureIndex:
            featureRecord = self.table.FeatureList.FeatureRecord[featureIdx]
            featureTag = featureRecord.FeatureTag
            scripts = features.get(featureTag, None)
            if scripts is None:
                scripts = OrderedDict()
                features[featureTag] = scripts

            languages = scripts.get(scriptTag, None)
            if languages is None:
                languages = OrderedDict()
                scripts[scriptTag] = languages

            lookups = languages.get(langTag, None)
            if lookups is None:
                lookups = []
                languages[langTag] = lookups

            for lookupIdx in featureRecord.Feature.LookupListIndex:
                lookups.append(lookupIdx)

    def collectFeatures(self):
        features = OrderedDict()
        for scriptRecord in self.table.ScriptList.ScriptRecord:
            scriptTag = scriptRecord.ScriptTag
            if scriptRecord.Script.DefaultLangSys is not None:
                self._prepareFeatureLangSys('dflt', scriptRecord.Script.DefaultLangSys, self.table, features, scriptTag)
            for langSysRecord in scriptRecord.Script.LangSysRecord:
                self._prepareFeatureLangSys(langSysRecord.LangSysTag, langSysRecord.LangSys, self.table, features, scriptTag)
        self.features = features

    def tidyFeatures(self):
        # Now tidy up. Most common case is a set of lookups duplicated to all language systems
        for name, feature in self.features.items():
            # print(feature["DFLT"]["dflt"])
            allLookups = [ langLookup for script in feature.values() for langLookup in script.values() ]
            lookupsAreEqual = [ x == allLookups[0] for x in allLookups ]
            if all(lookupsAreEqual):
                self.features[name] = { "DFLT": { "dflt": allLookups[0] }}

        # Also check for individual lookups which can be hoisted to default
        for name, feature in self.features.items():
            allLookups = [ langLookup for script in feature.values() for langLookup in script.values() ]
            for lookupIx in allLookups[0]:
                everyoneGetsIt = all([ lookupIx in x for x in allLookups ])
                if everyoneGetsIt and len(allLookups)>1:
                    for arr in allLookups[1:]:
                        arr.remove(lookupIx)

    def inlineFeatures(self):
        # Check which can be inlined and which are shared
        for name, feature in self.features.items():
            for script in feature.values():
                for langLookups in script.values():
                    for lookupIdx in langLookups:
                        self.lookups[lookupIdx]["useCount"] = self.lookups[lookupIdx]["useCount"]+1
                        if self.lookups[lookupIdx]["useCount"] > 1 and len(self.lookups[lookupIdx]["lookup"].statements) > 3:
                            self.lookups[lookupIdx]["inline"] = False
                            self.sharedLookups.add(lookupIdx)


    def addFeatures(self, doLookups = True):
        if doLookups:
            self.feature.statements.append(Comment('\n# Shared lookups\n'))
            for l in self.sharedLookups:
                self.feature.statements.append(self.lookups[l]["lookup"])

        for name, feature in self.features.items():
            f = FeatureBlock(name=name)
            for scriptname, langs in feature.items():
                for lang, lookups in langs.items():
                    if not (scriptname == "DFLT" and lang == "dflt"):
                        f.statements.append(Comment(""))
                        f.statements.append(ScriptStatement(scriptname))
                        f.statements.append(LanguageStatement(lang))
                    if doLookups:
                        for lookupIdx in lookups:
                            lookup = self.lookups[lookupIdx]["lookup"]
                            if self.lookups[lookupIdx]["inline"]:
                                for s in lookup.statements:
                                    f.statements.append(s)
                            else:
                                f.statements.append(LookupReferenceStatement(lookup))
            self.feature.statements.append(f)

    def unparseLookups(self):
        lookupOrder = range(0,len(self.table.LookupList.Lookup))
        # Reorder to check for dependencies
        newOrder = []
        while True:
            changed = False
            newOrder = []
            for lookupIdx in lookupOrder:
                lookup = self.table.LookupList.Lookup[lookupIdx]
                if self.isChaining(lookup.LookupType):
                    dependencies = self.getDependencies(lookup)
                    for l in dependencies:
                        if not l in newOrder:
                            newOrder.append(l)
                            changed = True
                if not lookupIdx in newOrder:
                    newOrder.append(lookupIdx)
            lookupOrder = newOrder
            if not changed:
                break

        for lookupIdx in lookupOrder:
            lookup = self.table.LookupList.Lookup[lookupIdx]
            res, dependencies = self.unparseLookup(lookup)
            self.lookups[lookupIdx] = {
                "lookup": res,
                "dependencies": dependencies,
                "useCount": 0,
                "inline": True
            }

    def unparseLookup(self, lookup):
        unparser = getattr(self, "unparse"+self.lookupTypes[lookup.LookupType])
        return unparser(lookup)

    def unparseExtension(self, lookup):
        for xt in lookup.SubTable:
            xt.SubTable = [ xt.ExtSubTable ]
            xt.LookupType = xt.ExtSubTable.LookupType
            return self.unparseLookup(xt)

    def asXML(self, sub):
        writer = XMLWriter(BytesIO())
        sub.toXML(writer, self.font)
        out = writer.file.getvalue().decode("utf-8")
        return out

    def unparsable(self, b, e, sub):
        b.statements.append(Comment("# XXX Unparsable rule: "+str(e)))
        b.statements.append(Comment("# ----"))
        out = self.asXML(sub).splitlines()
        for ln in out:
            b.statements.append(Comment("# "+ln))
        b.statements.append(Comment("# ----\n"))
