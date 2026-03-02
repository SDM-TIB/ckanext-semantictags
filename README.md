[![CKAN](https://img.shields.io/badge/ckan-2.10-orange.svg?style=flat-square)](https://github.com/ckan/ckan/tree/2.10) [![CKAN](https://img.shields.io/badge/ckan-2.9-orange.svg?style=flat-square)](https://github.com/ckan/ckan/tree/2.9)

# Semantic Tags

`ckanext-semantictags` is a CKAN extension that adds support for ontology-backed keywords for your datasets.
The extension reads the ontologies from the [TIB-hosted Terminology Service](https://terminology.tib.eu/ts/). 

## Installation

As usual for CKAN extensions, you can install `ckanext-semantictags` as follows:

```bash
git clone git@github.com:SDM-TIB/ckanext-semantictags.git
pip install -e ./ckanext-semantictags
pip install -r ./ckanext-semantictags/requirements.txt
```

## Configuration Options

- `ckanext.semantictags.ontologies` the ontologies to use for semantic tag suggestions
  - Default: (none)
- `ckanext.semantictags.allow_free_tags` whether to allow free-text tags in addition to ontology-based tags
  - Default: `false`
- `ckanext.semantictags.force_reload` whether to force a reload of the ontologies on startup, instead of using the cached version
  - Default: `false`

## Usage

In order to initialize the extension, add the following to your start-up scripts, assuming `$CKAN_INI` is the path of your CKAN configuration file:

```bash
ckan config-tool -s app:main $CKAN_INI "ckanext.semantictags.ontologies = YOUR_ONTOLOGY_SHORT_NAME"
ckan -c $CKAN_INI semantictags init --free-tags
```

Replace `YOUR_ONTOLOGY_SHORT_NAME` with the short name(s) of the ontology/ontologies you want to use, e.g. `oeo` for energy systems research related terms.

If you are using `ckanext-scheming`, change your `tag_string` field declaration to:
```yaml
- field_name: tag_string
  label: Tags
  form_snippet: form_snippets/semantictags_autocomplete.html
```

### Suggest Tags from Description

To enable automatic tag suggestions based on dataset descriptions, add the `suggest_tags_section` field to your `ckanext-scheming` configuration. Place it **above** the `tag_string` field:

```yaml
- field_name: suggest_tags_section
  label: Tag Suggestions
  form_snippet: form_snippets/semantictags_suggest_button.html

- field_name: tag_string
  label: Tags
  form_snippet: form_snippets/semantictags_autocomplete.html
```

This enables two buttons in your dataset form:
- **Suggest Tags**: analyzes the description text and suggests relevant tags using the [NFDI4Energy Annotator API](https://service.tib.eu/sandbox/nfdi4energyannotator/docs#/)
- **Clear Tags**: removes all tags with a single click

The suggested tags are filtered to only include terms from the configured ontologies.

## Commands

`ckanext-semantictags` offers the following commands, assuming `$CKAN_INI` is the path of your CKAN configuration file:

1. `init`: initializes the `ckanext-semantictags` runtime data: sets up the database table, ensures default configuration options are set, and generates the tag vocabulary.
   ```bash
   ckan -c $CKAN_INI semantictags init
   ```
   Optionally, default values for `allow_free_tags` and `force_reload` can be set to `true` via flags. These are only applied if no value was previously set in the CKAN configuration — existing configuration values take precedence.
   ```bash
   ckan -c $CKAN_INI semantictags init --free-tags --force-reload
   ```

## Changelog

If you are interested in what has changed, check out the [changelog](CHANGELOG.md).

## License

`ckanext-semantictags` is licensed under GPL-3.0, see the [license file](LICENSE).
