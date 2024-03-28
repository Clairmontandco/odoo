# -*- coding: utf-8 -*-

import logging

from datetime import date, datetime, timedelta

from odoo import _, api, fields, models

from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class joint_calendar(models.Model):
    """
    The model to combine various events by rules
    """
    _name = "joint.calendar"
    _description = "Joint Calendar"

    @api.constrains("days_before", "days_after", "time_limit")
    def _check_dates(self):
        """
        Constraint method for days_before, days_after, and time_limit
        """
        for calendar in self:
            if calendar.time_limit and (calendar.days_before <= 0 or calendar.days_after <= 0):
                raise UserError(_("Time Limits should be positive"))

    @api.constrains("default_alarm_ids")
    def _check_alarms(self):
        """
        Constraint method for days_before, days_after, and time_limit
        """
        for calendar in self:
            alarms_ids = calendar.default_alarm_ids.filtered(lambda ala: ala.alarm_type == "sms")
            if alarms_ids:
                raise UserError(_("At this moment sms alarms for joint events are not supported"))

    def _inverse_name(self):
        """
        Inverse method for name

        Attrs update:
         * menu_id.name
         * action_id.name
        """
        self = self.sudo()
        for calendar in self:
            if calendar.menu_id:
                calendar.menu_id.name = calendar.name
            if calendar.action_id:
                calendar.action_id.name = calendar.name

    def _inverse_sequence(self):
        """
        Inverse method for sequence
        """
        self = self.sudo()
        for calendar in self.sudo():
            if calendar.menu_id:
                calendar.menu_id.sequence = calendar.sequence

    def _inverse_activate_menu(self):
        """
        Inverse method for activate_menu
        The goal is to prepare an action and menu

        Methods:
         * _return_joint_action
        """
        self.sudo()
        for calendar in self:
            if calendar.activate_menu and not calendar.menu_id:
                action_data = calendar._return_joint_action()
                action_id = self.env["ir.actions.act_window"].create(action_data)
                parent_id = False
                if self.env.ref("joint_calendar.main_joint"):
                    parent_id = self.env.ref("joint_calendar.main_joint").id
                data = {
                    "name": calendar.name,
                    "parent_id": parent_id or False,
                    "sequence": calendar.sequence,
                    "action": "ir.actions.act_window, " + str(action_id.id),
                }
                if calendar.private_menu == "groups" and calendar.groups_ids:
                    data.update({"groups_id": [(6, 0, calendar.groups_ids.ids)]})
                menu_id = self.env["ir.ui.menu"].sudo().create(data)
                calendar.menu_id = menu_id
                calendar.action_id = action_id
            elif not calendar.activate_menu and calendar.menu_id:
                calendar.menu_id.unlink()
                if calendar.action_id:
                    calendar.action_id.unlink()

    def _inverse_menu_and_group(self):
        """
        Inverse method for private_menu and groups_ids
        """
        self = self.sudo()
        for calendar in self:
            if calendar.menu_id:
                if calendar.private_menu == "groups" and calendar.groups_ids:
                    calendar.menu_id.groups_id = [(6, 0, calendar.groups_ids.ids)]
                else:
                    calendar.menu_id.groups_id = [(6, 0, [])]

    def _inverse_company_id(self):
        """
        Inverse method for company_id to clear ir.ui.menu cache
        """
        self.env["ir.ui.menu"].clear_caches()

    name = fields.Char(
        string="Calendar Name",
        required=True,
        inverse=_inverse_name,
    )
    rule_ids = fields.Many2many(
        "event.rule",
        "join_calendar_event_rule_rel",
        "calendar_id",
        "rule_id",
        string="Rules",
        help="criteria to search objects for new events in this calendar",
        copy=True,
    )
    event_ids = fields.One2many(
        "joint.event",
        "joint_calendar_id",
        string="Joint Events",
        copy=False,
    )
    activate_menu = fields.Boolean(
        string="Active Menu",
        inverse=_inverse_activate_menu,
        default=True,
        help="""Check to have an active menu.
Uncheck to archive this Joint Calendar: no event would be generated furthermore""",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=50,
        inverse=_inverse_sequence,
        help="The lesser, the closer would be the menu for the top",
    )
    menu_id = fields.Many2one(
        "ir.ui.menu",
        string="Related Menu",
        ondelete="SET NULL",
        copy=False,
    )
    action_id = fields.Many2one(
        "ir.actions.act_window",
        string="Related Action",
        ondelete="SET NULL",
        copy=False,
    )
    days_before = fields.Integer(
        string="Days Before",
        default="10",
        help="Exclude outdated events. 'Start' is used to search events",
    )
    days_after = fields.Integer(
        string="Days After",
        default="30",
        help="Restrict events created by too distant objects. 'Start' is used to search events",
    )
    time_limit = fields.Boolean(
        string="Time Limits",
        default=True,
        help="To make events' update faster, limit the objects time range",
    )
    private_menu = fields.Selection(
        [
            ("public", "Public"),
            ("groups", "Private"),
        ],
        string="Privacy",
        required=True,
        default="public",
        inverse=_inverse_menu_and_group,
        help="""Select 'Public' to make the menu availbale for everybody.
Select 'Private' to choose to which groups this menu is available""",
    )
    groups_ids = fields.Many2many(
        "res.groups",
        string="Groups",
        inverse=_inverse_menu_and_group,
        help="Which user groups would see the related menu",
    )
    default_alarm_ids = fields.Many2many(
        "calendar.alarm",
        "calendar_alarm_joint_calendar_rel_sp",
        "joint_calen_rel",
        "alarm_sp_rel",
        string="Alarms",
        copy=False,
    )
    last_sync_date = fields.Datetime(
        string="Last Sync Time",
        default=lambda self: fields.Datetime.now(),
    )
    company_id = fields.Many2one(
        "res.company",
        default=False,
        required=False,
        help="Leave it empty to make the calendar global, so available for all companies",
        index=True,
        inverse=_inverse_company_id,
    )

    def unlink(self):
        """
        Re-write to unlink related menu, action and events
        """
        for cale in self:
            cale.menu_id.unlink()
            cale.action_id.unlink()
            cale.event_ids.unlink()
        return super(joint_calendar, self).unlink()

    @api.model
    def action_cron_update_events(self):
        """
        The method to generate events by active calendars

        Methods:
         * generate_events
        """
        calen_to_update = self.env["joint.calendar"].search([("activate_menu", "=", True)], order="last_sync_date, id")
        for cale in calen_to_update:
            cale.action_generate_events()

    def action_generate_events(self):
        """
        The method to generate events by this joint calendar
         1. Filter objects for events by introduced domain, company, and time limits
         2. Write in existing event and unlink events if target objects are not any more in joint calendar
         3. Create missing events
         4. Remove events that relate to the rules not any more present for the calendar

        Methods:
         * _return_rule_data
        """
        self = self.sudo()
        self = self.with_context(no_parent_updates=True)
        today_date = fields.Datetime.now()
        for calendar in self:
            last_date = False
            if calendar.time_limit:
                last_date = today_date + timedelta(days=calendar.days_after)
                first_date = today_date - timedelta(days=calendar.days_before)
            company_id = calendar.company_id
            rule_ids = self.env["event.rule"].search([("id", "in", calendar.rule_ids.ids)], order="last_sync_date, id")
            for rule in rule_ids:
                rule_obj = self.env[rule.res_model_domain]
                # 1
                domain = rule.domain and safe_eval(rule.domain) or []
                start_date_field = rule.field_start.name
                if last_date:
                    domain += [(start_date_field, "<=", last_date), (start_date_field, ">=", first_date)]
                if company_id and rule.fields_company_id:
                    domain += [(rule.fields_company_id.name, "=", company_id.id)]
                try:
                    objects = rule_obj.search(domain)
                except:
                    _logger.warning("Domain for joint events calendar is not correct: {}".format(domain))
                    objects = rule_obj.search([])
                # 2
                rule_existing_events = self.env["joint.event"].search([
                    ("joint_calendar_id", "=", calendar.id),
                    ("rule_id", "=", rule.id),
                ])
                to_delete_events = self.env["joint.event"]
                for event in rule_existing_events:
                    target_object = event.res_reference
                    if target_object and target_object in objects:
                        joint_event_data = calendar._return_rule_data(rule=rule, item=target_object)
                        event.write(joint_event_data)
                    else:
                        to_delete_events += event                   
                    if target_object:
                        objects -= target_object
                to_delete_events.unlink()
                # 3
                vals_list = []
                for item in objects:
                    joint_event_data = calendar._return_rule_data(rule=rule, item=item, create_mode=True)
                    vals_list.append(joint_event_data)
                if vals_list:
                    event_ids = self.env["joint.event"].create(vals_list)
                rule.write({"last_sync_date": fields.Datetime.now()})
                self.env.cr.commit()
            # 4
            obsolete_events = self.env["joint.event"].search([
                ("joint_calendar_id", "=", calendar.id), ("rule_id", "!=", False), ("rule_id", "not in", rule_ids.ids),
            ])
            obsolete_events.unlink()
            calendar.write({"last_sync_date": fields.Datetime.now()})
            self.env.cr.commit()

    def _return_joint_action(self):
        """
        The method to return an actio for activated joint calendar
        
        Args:
         * whether the form should be fist

        Returns:
         * dict

        Extra info:
         * Expected singleton
        """
        action_data = self.sudo().env.ref("joint_calendar.joint_event_action_full").read()[0]
        action_data["name"] = self.name
        action_data["domain"] = [("joint_calendar_id", "=", self.id)]
        action_data["context"] = {"default_joint_calendar_id": self.id}
        return action_data

    def _return_rule_data(self, rule, item, create_mode=False,):
        """
        Method to prepare vals for a joint event

        Args:
         * rule - event.rule object
         * item - target object record (as crm.lead)
         * create_mode - bool: whether we try to create

        Methods:
         * _convert_to_datetime

        Returns:
         * dict to write / to create joint event

        Extra info:
         * Expected singleton
        """
        joint_event_data = {
            "action": rule.action.id,
            "date_start": rule.field_start and self._convert_to_datetime(item[rule.field_start.name]) or False,
            "date_stop": rule.field_stop and self._convert_to_datetime(item[rule.field_stop.name]) or \
                         self._convert_to_datetime(item[rule.field_start.name]),
            "all_day": rule.always_all_day or rule.field_all_day and item[rule.field_all_day.name] or False,
            "date_delay": rule.field_delay and item[rule.field_delay.name] or False,
            "name": rule.field_name and item[rule.field_name.name] or _("Undefined"),
            "description": rule.field_description and item[rule.field_description.name] or False,
            "attendee": rule.field_atendees.relation == "res.users" \
                        and [(6, 0, item[rule.field_atendees.name].mapped("partner_id.id"))] \
                        or [(6, 0, item[rule.field_atendees.name].mapped("id"))],
            "partner_id": rule.fields_extra_partner_id \
                          and item[rule.fields_extra_partner_id.name].id \
                          or False,
            "company_id": rule.fields_company_id \
                          and item[rule.fields_company_id.name].id \
                          or False,
        }
        if create_mode:
            joint_event_data.update({
                "rule_id": rule.id,
                "joint_calendar_id": self.id,
                "res_id": item.id,
                "res_model": rule.res_model.id,
                "alarm_ids": [(6, 0, self.default_alarm_ids.ids)],
            })
        return joint_event_data

    @api.model
    def _convert_to_datetime(self, val_date):
        """
        The method to convert to-update-date into datetime (sometimes it is date)

        Args:
         * date - datetime or date

        Returns:
         * datetime.datetime
        """
        res = False
        if val_date:
            if isinstance(val_date, datetime):
                res = val_date
            else:
                res = datetime.combine(val_date, datetime.min.time())
        return res
