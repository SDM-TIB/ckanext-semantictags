this.ckan.module('semantictags-clear-tags', function ($) {
  return {
    options: {
      tagStringFieldSelector: '#field-tags',
      buttonText: 'Clear Tags',
    },

    initialize: function () {
      var self = this;

      console.log('semantictags-clear-tags module initialized on', this.el);

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
      var self = this;
      var tagStringField = $(this.options.tagStringFieldSelector);

      if (!tagStringField.length) {
        alert('Tags field not found');
        return;
      }

      var currentValue = tagStringField.val();
      if (!currentValue || currentValue.trim() === '') {
        self._showNotification('No tags to clear', 'info');
        return;
      }

      tagStringField.val('').change();
      self._showNotification('All tags have been cleared', 'success');
    },

    _showNotification: function (message, type) {
      var alertClass = type === 'success' ? 'alert-success' : (type === 'info' ? 'alert-info' : 'alert-danger');
      var alertHtml = '<div class="alert ' + alertClass + ' alert-dismissible" style="margin-top: 10px;">' +
        '<button type="button" class="close" data-dismiss="alert">&times;</button>' +
        message +
        '</div>';

      var formGroup = this.el.closest('.form-group');
      if (formGroup.length) {
        formGroup.after(alertHtml);
      } else {
        this.el.after(alertHtml);
      }

      setTimeout(function () {
        $('.alert-dismissible').fadeOut(function () {
          $(this).remove();
        });
      }, 4000);
    }
  };
});
