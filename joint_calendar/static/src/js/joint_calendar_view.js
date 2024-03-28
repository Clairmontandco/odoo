/** @odoo-module **/

import CalendarRenderer from 'web.CalendarRenderer';
import CalendarController from 'web.CalendarController';
import CalendarView from 'web.CalendarView';
import viewRegistry from 'web.view_registry';

const jointCalendarController = CalendarController.extend({
    custom_events: _.extend({}, CalendarController.prototype.custom_events, {
        refreshJointCalendar: '_onRefreshJointCalendar',
    }),
    _onRefreshJointCalendar: function (event) {
        var self = this;
        this._rpc({
            model: "joint.calendar",
            method: "action_generate_events",
            args: [[self.context.default_joint_calendar_id]],
            context: self.context,
        }).then(function (res) {
            self.reload();
        }).then(event.data.on_always, event.data.on_always);
    }
});

const jointCalendarRenderer = CalendarRenderer.extend({
    events: _.extend({}, CalendarRenderer.prototype.events, {
        'click .refresh_joint': '_onRefreshJointCalendar',
    }),
    _initSidebar: function () {
        var self = this;
        this._super.apply(this, arguments);
        this.$refreshButton = $('<button/>', {type: 'button'})
                            .addClass('refresh_joint oe_button btn btn-secondary')
                            .prepend($('<span><i class="fa fa-refresh mr4"></i> Refresh</span>'))
                            .appendTo(self.$sidebar);
    },
    _onRefreshJointCalendar: function () {
        var self = this;
        var context = this.getSession().user_context;
        this.$refreshButton.prop('disabled', true);
        this.trigger_up('refreshJointCalendar', {
            on_always: function () {
                self.$refreshButton.prop('disabled', false);
            },
        });
    },
});

const jointCalendarView = CalendarView.extend({
    config: _.extend({}, CalendarView.prototype.config, {
        Controller: jointCalendarController,
        Renderer: jointCalendarRenderer,
    }),
});

viewRegistry.add('joint_calendar', jointCalendarView);

export default {
    jointCalendarController: jointCalendarController,
    jointCalendarRenderer: jointCalendarRenderer,
    jointCalendarView: jointCalendarView
};
