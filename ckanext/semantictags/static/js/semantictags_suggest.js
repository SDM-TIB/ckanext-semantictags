this.ckan.module('semantictags-suggest', function ($) {
  return {
    options: {
      notesFieldSelector: '#field-notes',
      tagStringFieldSelector: '#field-tags',
      buttonText: 'Suggest',
    },

    initialize: function () {
      var self = this;
      this.isLoading = false;
      this.notesField = $(this.options.notesFieldSelector);

      // Create and attach the suggest button (only if not already present)
      this._createSuggestButton();

      // Initial button state based on notes field content
      this._updateButtonState();

      // Listen for changes in the notes field
      this.notesField.on('input change', function () {
        self._updateButtonState();
      });

      // Attach event listener to the container/button
      this.el.on('click', function (e) {
        if (e.target.tagName === 'BUTTON' && !e.target.disabled) {
          e.preventDefault();
          self._suggestTags();
        }
      });
    },

    teardown: function () {
      this.el.off('click');
      this.notesField.off('input change');
    },

    _updateButtonState: function () {
      var btn = this.el.find('button');
      var text = this.notesField.val() || this.notesField.text();
      var hasText = text && text.trim().length > 0;

      if (this.isLoading) {
        btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + this.options.buttonText);
      } else {
        btn.html(this.options.buttonText);
        if (hasText) {
          btn.prop('disabled', false).addClass('btn-primary').removeClass('btn-default');
        } else {
          btn.prop('disabled', true).addClass('btn-default').removeClass('btn-primary');
        }
      }
    },

    _createSuggestButton: function () {
      if (this.el.find('button').length) {
        return;
      }
      var buttonHtml = '<button type="button" class="btn btn-default semantictags-suggest-btn" style="margin-top: 5px;">' +
        this.options.buttonText + '</button>';
      this.el.html(buttonHtml);
    },

    _suggestTags: function () {
      var self = this;
      if (this.isLoading) return;

      var notesField = $(this.options.notesFieldSelector);
      var tagStringField = $(this.options.tagStringFieldSelector);

      if (!notesField.length) {
        alert('Description field not found');
        return;
      }

      var text = notesField.val() || notesField.text();
      if (!text || !text.trim()) {
        alert('Please enter a description before requesting tag suggestions');
        return;
      }

      this.isLoading = true;
      this._updateButtonState();

      this.sandbox.client.call(
          'POST',
          'semantictags_suggest_tags',
          { text: text },
          function (response) {
            if (response.success && !response.result.error) {
              self._populateTags(response.result.suggestions, tagStringField);
              self._showNotification('Tags suggested successfully', 'success');
            } else {
              var msg = (response.result && response.result.error) || response.error || 'Unknown error';
              self._showNotification('Failed to suggest tags: ' + msg, 'error');
            }
            self.isLoading = false;
            self._updateButtonState();
          },
          function (error) {
            self._showNotification('Error: ' + error, 'error');
            self.isLoading = false;
            self._updateButtonState();
          }
      );
    },

    _populateTags: function (suggestions, tagStringField) {
      if (!suggestions || suggestions.length === 0) {
        alert('No tags suggested');
        return;
      }

      var existingTags = tagStringField.val() ? tagStringField.val().split(',') : [];
      var existingTagNames = new Set(existingTags.map(function (t) { return t.trim().toLowerCase(); }));

      var newTags = [];
      suggestions.forEach(function (tag) {
        var tagName = tag.label || tag.name;
        if (tagName && !existingTagNames.has(tagName.toLowerCase())) {
          newTags.push(tagName);
        }
      });

      if (newTags.length === 0) {
        alert('All suggested tags already exist');
        return;
      }

      var allTags = existingTags.concat(newTags);
      tagStringField.val(allTags.join(', ')).change();
    },

    _showNotification: function (message, type) {
      let container = document.querySelector('.flash-messages');
      if (!container) return;

      let success = type === 'success'

      let alertEl = document.createElement('div');
      alertEl.className = 'alert alert-dismissible fade show ' + (success ? 'alert-success' : 'alert-danger');

      let btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-close close';
      btn.setAttribute('data-bs-dismiss', 'alert');
      btn.setAttribute('aria-label', 'Close');

      let text = document.createTextNode(message);

      alertEl.appendChild(text);
      alertEl.appendChild(btn);

      container.appendChild(alertEl);

      if (success) {
        setTimeout(function() {
          $('.alert-dismissible').fadeOut(function() {
            $(this).remove();
          });
        }, 5000);
      }
    }
  };
});
