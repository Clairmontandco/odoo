# -*- coding: utf-8 -*-
# Part of Keypress IT Services. See LICENSE file for full copyright and licensing details.##
##################################################################################
from odoo import models

class mrp_production(models.Model):
    _inherit = 'mrp.production'

    def kits_cancel_manufacture(self):
        for record in self:
            if record.state == 'done':
                record.move_finished_ids.stock_quant_update_spt()
                record.move_raw_ids.stock_quant_update_spt()
                record.action_cancel()
            elif record.state == 'cancel':
                continue
            else:
                record.action_cancel()

