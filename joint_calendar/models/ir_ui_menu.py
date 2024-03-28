# -*- coding: utf-8 -*-

from odoo import api, models, tools
from odoo.http import request


def CachedOMM(method):
    """
    The decorator used to check whether companies have been changed, and if yes, to clear ir.ui.menu cache
    In this way, load_menus and get_omm_current_companies would be cleared on any company change (including new tab 
    open). So, menus would be recalculated
    """
    def wrapper(self, debug):
        """
        The wrapper method itself that is designed for load_menus

        Methods:
         * get_omm_current_companies
         * _get_omm_current_companies
         * clear_caches (@see odoo>odoo>models.py)
        """
        if  self._get_omm_current_companies() != self.get_omm_current_companies():
            self.env["ir.ui.menu"].clear_caches()
        return method(self, debug)
    return wrapper

class ir_ui_menu(models.Model):
    """
    Overwrite to add the features to block meny by companies

    Important: the overwriting is made compatibable with the module odoo_menu_management to avoid too frequent updates
    So, the method are purposefully called and cached exactly the same in the modules, altough they do not depend
    on each other
    """
    _inherit = "ir.ui.menu"

    @CachedOMM
    @api.model
    @tools.ormcache_context("self._uid", "debug", keys=("lang",))
    def load_menus(self, debug):
        """
        Re-write specifically to add the decorator to clear cache
        """
        return super(ir_ui_menu, self).load_menus(debug=debug)

    @tools.ormcache("self._uid")
    def get_omm_current_companies(self):
        """
        The method to calculate available companies
        IMPORTANT: This method assumes saving companies to registry CACHE. 
        Thus, _get_omm_current_companies and get_omm_current_companies might result in different string

        Methods:
         * get_omm_current_companies

        Returns:
         * str
        """
        return self._get_omm_current_companies()

    def _get_omm_current_companies(self):
        """
        The method to calculate available companies

        Returns: 
         * str
        """
        return request.httprequest.cookies.get("cids", str(self.env.user.company_id.id))

    def _load_menus_blacklist(self):
        """
        Re-write to block joint calendar-related menus
 
        Methods:
         * _get_joint_blacklisted
        """
        res = super()._load_menus_blacklist()
        not_shown_menus = self._get_joint_blacklisted()
        return res + not_shown_menus

    @api.model
    def _get_joint_blacklisted(self):
        """
        The method to find all joint calendars that are not compatibable with the current company

        Methods:
         * get_joint_companies

        Returns:
         * list of ints (of blocked ir.ui.menu records)
        """
        not_shown_menus = []
        allowed_companies = self.get_omm_current_companies()
        allowed_company_ids = [int(cid) for cid in allowed_companies.split(",")]
        not_shown_calendars = self.sudo().env["joint.calendar"].search([
            ("company_id", "!=", False),
            ("company_id", "not in", allowed_company_ids),
        ])
        if not_shown_calendars:
            not_shown_menus = not_shown_calendars.mapped("menu_id").ids
        return not_shown_menus
