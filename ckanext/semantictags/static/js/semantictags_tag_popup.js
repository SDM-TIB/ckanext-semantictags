this.ckan.module('semantictags-tag-popup', function ($) {
  return {
    options: {
      iri: null,
    },

    initialize: function () {
      var self = this;

      this._tooltip = null;
      this._fetchState = 'idle'; // idle | loading | done | error
      this._data = null;

      this.el.on('mouseenter', function (e) { self._onEnter(e); });
      this.el.on('mouseleave', function () { self._onLeave(); });
    },

    teardown: function () {
      this._removeTooltip();
      this.el.off('mouseenter mouseleave');
    },

    _onEnter: function (e) {
      this._showTooltip(e);

      if (!this.options.iri) {
        this._fetchState = 'done';
        this._data = null;
        this._updateTooltipContent(this._renderNoInfo());
        return;
      }

      if (this._fetchState === 'idle') {
        this._fetchState = 'loading';
        this._updateTooltipContent(this._renderLoading());
        this._fetchDetails();
      } else if (this._fetchState === 'done' || this._fetchState === 'error') {
        this._updateTooltipContent(this._renderData());
      }
    },

    _renderNoInfo: function () {
      return $('<div>')
        .addClass('semantictags-tooltip__no-info')
        .text('No ontology information available.');
    },

    _onLeave: function () {
      this._removeTooltip();
    },

    _fetchDetails: function () {
      var self = this;
      var iri = this.options.iri;
      if (!iri) {
        this._fetchState = 'error';
        this._data = { error: 'No IRI available' };
        this._updateTooltipContent(this._renderData());
        return;
      }

      $.ajax({
        url: '/api/3/action/semantictags_term_details',
        data: { iri: iri },
        dataType: 'json',
        success: function (response) {
          self._fetchState = 'done';
          self._data = response.result || { error: 'No data returned' };
          self._updateTooltipContent(self._renderData());
        },
        error: function () {
          self._fetchState = 'error';
          self._data = { error: 'Request failed' };
          self._updateTooltipContent(self._renderData());
        },
      });
    },

    _showTooltip: function (e) {
      if (this._tooltip) return;

      var tooltip = $('<div>')
          .addClass('semantictags-tooltip')
          .append(this._renderLoading());

      $('body').append(tooltip);
      this._tooltip = tooltip;
      this._positionTooltip(e);
    },

    _positionTooltip: function (e) {
      if (!this._tooltip) return;

      var offset = this.el.offset();
      var elHeight = this.el.outerHeight();

      this._tooltip.css({
        top: offset.top + elHeight + 6,
        left: offset.left,
      });
    },

    _updateTooltipContent: function (html) {
      if (this._tooltip) {
        this._tooltip.empty().append(html);
      }
    },

    _removeTooltip: function () {
      if (this._tooltip) {
        this._tooltip.remove();
        this._tooltip = null;
      }
    },

    _renderLoading: function () {
      return $('<div>').addClass('semantictags-tooltip__loading').text('Loading...');
    },

    _renderData: function () {
      var d = this._data;
      if (!d || d.error) {
        return $('<div>')
            .addClass('semantictags-tooltip__error')
            .text(d ? d.error : 'Unknown error');
      }

      var container = $('<div>').addClass('semantictags-tooltip__body');

      if (d.label) {
        container.append(this._renderRow('Label', d.label));
      }

      if (d.definition) {
        container.append(this._renderRow('Description', d.definition));
      }

      if (d.curie) {
        container.append(
            this._renderRow(
                'CURIE',
                $('<span>').addClass('semantictags-tooltip__badge semantictags-tooltip__badge--curie').text(d.curie)
            )
        );
      }

      if (d.ontology_name) {
        container.append(
            this._renderRow(
                'Defined in',
                $('<span>').addClass('semantictags-tooltip__badge semantictags-tooltip__badge--ontology').text(d.ontology_name.toUpperCase())
            )
        );
      }

      return container;
    },

    _renderRow: function (key, value) {
      var row = $('<div>').addClass('semantictags-tooltip__row');
      row.append($('<span>').addClass('semantictags-tooltip__key').text(key + ': '));
      if (typeof value === 'string') {
        row.append($('<span>').addClass('semantictags-tooltip__value').text(value));
      } else {
        row.append(value);
      }
      return row;
    },
  };
});
