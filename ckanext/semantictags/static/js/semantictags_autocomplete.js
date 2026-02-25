this.ckan.module('semantictags-autocomplete', function ($) {
  return {
    options: {
      source: null,
      createtags: false,
      tags: false,
    },

    initialize: function () {
      var self = this;
      var source = this.options.source || '';
      var allowCreate = String(this.options.createtags).toLowerCase() === 'true';
      var baseUrl = source.split('?')[0];

      this.el.select2({
        width: 'resolve',
        tags: allowCreate,
        tokenSeparators: [','],

        createSearchChoice: allowCreate ? function (term, data) {
          var exists = $(data).filter(function () {
            return this.text.localeCompare(term) === 0;
          }).length;
          if (!exists) {
            return { id: term, text: term };
          }
        } : undefined,

        ajax: {
          url: baseUrl,
          dataType: 'json',
          quietMillis: 200,
          data: function (term) {
            return { incomplete: term, limit: 10 };
          },
          results: function (data) {
            var items = (data.result || []).map(function (item) {
              if (typeof item === 'string') {
                return { id: item, text: item, ontology: '' };
              }
              return item;
            });
            return { results: items };
          },
        },

        formatResult: function (item) {
          var label = self._escapeHtml(item.text || item.id);
          var ontology = self._escapeHtml(item.ontology || '');
          if (ontology) {
            return (
                '<span class="semantictags-result">' +
                '<span class="semantictags-result__label">' + label + '</span>' +
                '<span class="semantictags-result__ontology">' + ontology + '</span>' +
                '</span>'
            );
          }
          return '<span class="semantictags-result__label">' + label + '</span>';
        },

        formatSelection: function (item) {
          return self._escapeHtml(item.text || item.id);
        },

        initSelection: function (element, callback) {
          var value = element.val();
          if (value) {
            var tags = value.split(',').map(function (v) {
              v = v.trim();
              return { id: v, text: v };
            });
            callback(tags);
          }
        },

        escapeMarkup: function (m) { return m; },
      });
    },

    _escapeHtml: function (str) {
      return String(str)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
    },
  };
});
