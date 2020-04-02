from fontTools.misc.py23 import *
import fontTools
from collections import OrderedDict
from .GTableUnparser import GTableUnparser
import fontFeatures
from itertools import groupby

def _invertClassDef(a, coverage = None):
    defs = {k: sorted([j for j, _ in list(v)]) for k, v in groupby(a.items(), lambda x: x[1])}
    if coverage:
        defs[0] = set(coverage) - set(a.keys())
    return defs

class GPOSUnparser (GTableUnparser):
    lookupTypes = {
        1: "SinglePositioning",
        2: "PairPositioning",
        3: "CursiveAttachment",
        4: "MarkToBase",
        5: "MarkToLigature",
        6: "MarkToMark",
        7: "ContextualPositioning",
        8: "ChainedContextualPositioning",
        9: "Extension"
    }

    def makeValueRecord(self, valueRecord, valueFormat):
        valueFormatFlags = (
            ('XPlacement', 0x0001) # Includes horizontal adjustment for placement
          , ('YPlacement', 0x0002) # Includes vertical adjustment for placement
          , ('XAdvance', 0x0004)   # Includes horizontal adjustment for advance
          , ('YAdvance', 0x0008)   # Includes vertical adjustment for advance
          , ('XPlaDevice', 0x0010) # Includes horizontal Device table for placement
          , ('YPlaDevice', 0x0020) # Includes vertical Device table for placement
          , ('XAdvDevice', 0x0040) # Includes horizontal Device table for advance
          , ('YAdvDevice', 0x0080) # Includes vertical Device table for advance
        # , 'Reserved': 0xF000 For future use (set to zero)
        )

        # defaults to 0
        # NOTE: this is likely not correct anymore when we start doing the
        # <device> tables in Value record format C.
        values = [getattr(valueRecord, name, 0) or None for name, _ in valueFormatFlags]
        return fontFeatures.ValueRecord(*values)

    def isChaining(self, lookupType):
        return lookupType == 7 or lookupType == 8

    def getDependencies(self, lookup):
        return []

    def unparseSinglePositioning(self, lookup):
        b = fontFeatures.Routine(name='SinglePositioning'+self.gensym())

        for subtable in lookup.SubTable:
            if subtable.Format == 1:
                spos = fontFeatures.Positioning(
                        [subtable.Coverage.glyphs],
                        [self.makeValueRecord(subtable.Value, subtable.ValueFormat)]
                )
                b.addRule(spos)
            else:
                # Optimize it later
                for g,v in zip(subtable.Coverage.glyphs, subtable.Value):
                    spos = fontFeatures.Positioning(
                            [[g]],
                            [self.makeValueRecord(v, subtable.ValueFormat)]
                    )
                    b.addRule(spos)
        return b, []

    def unparsePairPositioning(self, lookup):
        b = fontFeatures.Routine(name='PairPositioning'+self.gensym())
        for subtable in lookup.SubTable:
            if subtable.Format == 1:
                for g, pair in zip(subtable.Coverage.glyphs, subtable.PairSet):
                    for vr in pair.PairValueRecord:
                        spos = fontFeatures.Positioning(
                            [[g], [vr.SecondGlyph]],
                            [self.makeValueRecord(vr.Value1, subtable.ValueFormat1),
                             self.makeValueRecord(vr.Value2, subtable.ValueFormat2)]
                        )
                        b.addRule(spos)
            else:
                class1 = _invertClassDef(subtable.ClassDef1.classDefs, subtable.Coverage.glyphs)
                class2 = _invertClassDef(subtable.ClassDef2.classDefs)
                for ix1, c1 in enumerate(subtable.Class1Record):
                    if not ix1 in class1: continue # XXX
                    for ix2, c2 in enumerate(c1.Class2Record):
                        if not ix2 in class2: continue # XXX
                        vr1 = self.makeValueRecord(c2.Value1, subtable.ValueFormat1)
                        vr2 = self.makeValueRecord(c2.Value2, subtable.ValueFormat2)
                        if not vr1 and not vr2: continue
                        spos = fontFeatures.Positioning(
                            [class1[ix1], class2[ix2]],
                            [vr1,vr2]
                        )
                        b.addRule(spos)
        return b, []

    def unparseCursiveAttachment(self, lookup):
        b = fontFeatures.Routine(name='CursiveAttachment'+self.gensym())
        for s in lookup.SubTable:
            assert s.Format == 1
            for glyph, record in zip(s.Coverage.glyphs, s.EntryExitRecord):
                entryanchor = None
                exitanchor = None
                if record.EntryAnchor:
                    entryanchor = Anchor(record.EntryAnchor.XCoordinate, record.EntryAnchor.YCoordinate)
                if record.ExitAnchor:
                    exitanchor = Anchor(record.ExitAnchor.XCoordinate, record.ExitAnchor.YCoordinate)
                b.statements.append(CursivePosStatement(GlyphName(glyph), entryanchor, exitanchor))
        return b, []

    def unparseMarkToBase(self, lookup):
        b = fontFeatures.Routine(name='MarkToBase'+self.gensym())
        # self.unparsable(b, "Mark to base pos", lookup)
        for subtable in lookup.SubTable: # fontTools.ttLib.tables.otTables.MarkBasePos
            assert subtable.Format == 1
            anchorClassPrefix = 'Anchor'+self.gensym()
            definitions = self.formatMarkArray(subtable.MarkArray, subtable.MarkCoverage, anchorClassPrefix)
            bases = self.formatBaseArray(subtable.BaseArray, subtable.BaseCoverage, anchorClassPrefix)
        for d in definitions:
            b.statements.append(d)
        for d in bases:
            b.statements.append(d)

        return b, []

    def formatMarkArray(self, markArray, markCoverage, anchorClassPrefix):
        id2Name = markCoverage.glyphs
        markClasses = {}
        for i, markRecord in enumerate(markArray.MarkRecord):
            anchorclass = anchorClassPrefix + "_" + str(markRecord.Class)
            thisAnchor = (anchorclass,markRecord.MarkAnchor.XCoordinate, markRecord.MarkAnchor.YCoordinate)
            anchor = Anchor(thisAnchor[1],thisAnchor[2])
            # XXX I removed  contourpoint=hasattr(markRecord.MarkAnchor, "AnchorPoint") and markRecord.MarkAnchor.AnchorPoint or None)
            if not thisAnchor in markClasses:
                markClasses[thisAnchor] = { "class": MarkClass(anchorclass), "anchor": anchor, "glyphs": [] }

            markClasses[thisAnchor]["glyphs"].append(id2Name[i])

        for k,v in markClasses.items():
            definition = MarkClassDefinition(v["class"], v["anchor"], self.makeGlyphClass(v["glyphs"]))
            v["class"].addDefinition(definition)
        return [v["class"] for v in markClasses.values()]

    def formatBaseArray(self, baseArray, baseCoverage, anchorClassPrefix):
        id2Name = baseCoverage.glyphs
        bases = {}
        for i, baseRecord in enumerate(baseArray.BaseRecord):
            anchors = []
            for classId, anchor in enumerate(baseRecord.BaseAnchor):
                anchors.append((Anchor(anchor.XCoordinate, anchor.YCoordinate),GlyphClassDefinition(anchorClassPrefix + "_" + str(classId),[])))
            if not tuple(anchors) in bases:
                bases[tuple(anchors)] = []
            bases[tuple(anchors)].append(id2Name[i])
        markbasepos = []
        for k,v in bases.items():
            markbasepos.append(MarkBasePosStatement(self.makeGlyphClass(v), list(k)))
        return markbasepos

    def unparseMarkToLigature(self, lookup):
        b = fontFeatures.Routine(name='MarkToLigature'+self.gensym())
        self.unparsable(b, "Mark to lig pos", lookup)
        return b, []

    def unparseMarkToMark(self, lookup):
        b = fontFeatures.Routine(name='MarkToMark'+self.gensym())
        self.unparsable(b, "Mark to Mark pos", lookup)
        return b, []

    def unparseContextualPositioning(self, lookup):
        b = fontFeatures.Routine(name='ContextualPositioning'+self.gensym())
        self.unparsable(b, "Contextual pos", lookup)
        return b, []

    def unparseChainedContextualPositioning(self, lookup):
        b = fontFeatures.Routine(name='ChainedContextualPositioning'+self.gensym())
        # self.unparsable(b, "Chained Contextual pos", lookup)
        return b, []