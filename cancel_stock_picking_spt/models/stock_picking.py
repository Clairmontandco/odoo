# -*- coding: utf-8 -*-
# Part of Keypress IT Services. See LICENSE file for full copyright and licensing details.##
##################################################################################
from odoo import models


class stock_picking(models.Model):
    _inherit = 'stock.picking'

    def all_picking_cancle_spt(self):
        for rec in self:
            if rec.state == 'done':
                rec.picking_cancel_spt()

    def picking_cancel_spt(self):
        for stock_picking in self:
            stock_picking.move_lines.stock_quant_update_spt()
