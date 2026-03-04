this.ckan.module('semantictags-clear-tags', function ($) {
  return {
    options: {
      tagStringFieldSelector: '#field-tags',
      buttonText: 'Clear',
    },

    initialize: function () {
      var self = this;

      this._createClearButton();

      this.el.on('click', function (e) {
        if (e.target.tagName === 'BUTTON') {
          e.preventDefault();
          self._clearTags();
        }
      });
    },

    teardown: function () {
      this.el.off('click');
    },

    _createClearButton: function () {
      if (this.el.find('button').length) {
        return;
      }
      var buttonHtml = '<button type="button" class="btn btn-default semantictags-clear-tags-btn" style="margin-top: 5px; margin-left: 5px;">' +
        this.options.buttonText + '</button>';
      this.el.html(buttonHtml);
    },

    _clearTags: function () {
      var tagStringField = $(this.options.tagStringFieldSelector);

      if (!tagStringField.length) return;

      var currentValue = tagStringField.val();
      if (!currentValue || currentValue.trim() === '') return;

      tagStringField.val('').change();
    }
  };
});
