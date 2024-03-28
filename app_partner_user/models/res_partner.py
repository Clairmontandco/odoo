# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_user = fields.Boolean(string='Is a Internal User', default=False, readonly=True, copy=False,
                          help="Technical field used to get whether this partner is a user")
    related_user_id = fields.Many2one('res.users', string='Related User', readonly=True, copy=False)

    # 不可使用 compute，因为要用在 domain
    # user = fields.Boolean(string='Is a Internal User', compute='_compute_user', store=True,
    #                       help='Technical field used to get whether this partner is a user')
    # related_user_id = fields.Many2one('res.users', string='Related User', compute='_compute_user')
    #
    #
    # def _compute_user(self):
    #     for rec in self:
    #         r_user = self.env['res.users'].search([('partner_id', '=', rec.id)], limit=1)
    #         if r_user and len(r_user):
    #             rec.user = True
    #             rec.related_user_id = r_user
