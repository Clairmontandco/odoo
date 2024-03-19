# -*- coding: utf-8 -*-
# Part of Keypress IT Services. See LICENSE file for full copyright and licensing details.##
##################################################################################
from odoo import _,models
from odoo.exceptions import UserError

class stock_picking(models.Model):
    _inherit = 'stock.picking'

    def all_picking_cancel_spt(self):
        for rec in self:
            if rec.state == 'done':
                rec.picking_cancel_spt()

    def picking_cancel_spt(self):
        for stock_picking in self:
            stock_picking.move_ids_without_package.stock_quant_update_spt()

    def unlink(self):
        for moves in self.move_ids_without_package:
            if any(move.state == 'done' and not move.scrapped for move in moves):
                raise UserError(_('You cannot cancel a stock move that has been set to \'Done\'. Create a return in order to reverse the moves which took place.'))
        res = super(stock_picking,self).unlink()
        return res