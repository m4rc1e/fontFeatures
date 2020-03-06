# fontFeatures: Python library for manipulating OpenType font features

OpenType fonts are "programmed" using features, which are normally authored in Adobe's [feature file format](http://adobe-type-tools.github.io/afdko/OpenTypeFeatureFileSpecification.html). This like source code to a computer program: it's a user-friendly, but computer-unfriendly, way to represent the features.

Inside a font, the features are compiled in an efficient [internal format](https://simoncozens.github.io/fonts-and-layout/features.html#how-features-are-stored). This is like the binary of a computer program: computers can use it, but they can't do else anything with it, and people can't read it.

The purpose of this library is to provide a middle ground for representing features in a machine-manipulable format, kind of like the abstract syntax tree of a computer programmer. This is so that:

* features can be represented in a structured human-readable *and* machine-readable way, analogous to the XML files of the [Unified Font Object](http://unifiedfontobject.org/) format.
* features can be more directly authored by programs (such as font editors), rather than them having to output AFDKO feature file format.
* features can be easily manipulated by programs - for example, features from two files merged together, or lookups moved between languages.

> How is this different from fontTool's `feaLib`? I'm glad you asked. `feaLib` translates between the Adobe feature file format and a abstract syntax tree representing *elements of the feature file* - not representing the feature data. The AST is still "source equivalent". For example, when you code an `aalt` feature in feature file format, you might include code like `feature salt` to include lookups from another feature. But what's actually *meant* by that is a set of lookups. `fontFeatures` allows you to manipulate meaning, not description.

When completed, fontFeatures will comprise translators between the Adobe feature file format, the OTF internal representation and our own machine-manipulable representation.

Currently, I have implemented an OTF-to-Adobe translator, which you can find as `otf2fea.py`