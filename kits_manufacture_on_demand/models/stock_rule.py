from odoo import models , api, SUPERUSER_ID, _
from collections import defaultdict
from odoo.tools import float_compare
from odoo.addons.stock.models.stock_rule import ProcurementException



class stock_rule(models.Model):
    _inherit = 'stock.rule'

    @api.model
    def _run_manufacture(self, procurements):
        errors = []
        create_production = self.env['ir.config_parameter'].sudo().get_param('kits_manufacture_on_demand.create_production')
        #If Custom setting is not enable, default flow will execute.Otherwise, _run_manufacture will be by pass.    
        # if not create_production:
        productions_values_by_company = defaultdict(list)
        for procurement, rule in procurements:
            #if custom boolean is not checked.Then, default manufacture flow will create procurement. Otherwise, product will be skipped.
            if not procurement.product_id.kits_manufacture_ok or not create_production:
                if float_compare(procurement.product_qty, 0, precision_rounding=procurement.product_uom.rounding) <= 0:
                    # If procurement contains negative quantity, don't create a MO that would be for a negative value.
                    continue
                bom = rule._get_matching_bom(procurement.product_id, procurement.company_id, procurement.values)

                productions_values_by_company[procurement.company_id.id].append(rule._prepare_mo_vals(*procurement, bom))
        if errors:
            raise ProcurementException(errors)

        for company_id, productions_values in productions_values_by_company.items():
            # create the MO as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
            productions = self.env['mrp.production'].with_user(SUPERUSER_ID).sudo().with_company(company_id).create(productions_values)
            self.env['stock.move'].sudo().create(productions._get_moves_raw_values())
            self.env['stock.move'].sudo().create(productions._get_moves_finished_values())
            productions._create_workorder()
            productions.filtered(self._should_auto_confirm_procurement_mo).action_confirm()

            for production in productions:
                origin_production = production.move_dest_ids and production.move_dest_ids[0].raw_material_production_id or False
                orderpoint = production.orderpoint_id
                if orderpoint and orderpoint.create_uid.id == SUPERUSER_ID and orderpoint.trigger == 'manual':
                    production.message_post(
                        body=_('This production order has been created from Replenishment Report.'),
                        message_type='comment',
                        subtype_xmlid='mail.mt_note')
                elif orderpoint:
                    production.message_post_with_view(
                        'mail.message_origin_link',
                        values={'self': production, 'origin': orderpoint},
                        subtype_id=self.env.ref('mail.mt_note').id)
                elif origin_production:
                    production.message_post_with_view(
                        'mail.message_origin_link',
                        values={'self': production, 'origin': origin_production},
                        subtype_id=self.env.ref('mail.mt_note').id)
        return True