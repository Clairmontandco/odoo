# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.calendar.controllers.main import CalendarController


class JointCalendarController(CalendarController):
    """
    Re-write to add check by joint calendar notifications
    """

    @http.route("/joint_calendar/notify", type="json", auth="user")
    def notify_joint(self):
        """
        Joint events notifications route
        """
        return request.env["calendar.alarm_manager"].get_next_notif_joint()

    @http.route("/joint_calendar/event/get/action", type="json", auth="user")
    def get_joint_event_action(self, event_id):
        """
        Remove alarm task
        """
        res = True
        try:
            res = request.env.ref("joint_calendar.joint_event_action").read()[0]
            res["res_id"] = event_id
        except:
            res = False
        return res
