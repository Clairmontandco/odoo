import odoo
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class SaleReport(models.Model):
    _inherit = 'sale.report'

    mk_instance_id = fields.Many2one('mk.instance', "Instance", readonly=True)
    marketplace_type = fields.Char("Marketplace", readonly=True)
    delivery_amount = fields.Float('Delivery Amount', readonly=True)
    product_type = fields.Char("Product Type", readonly=True)

    def _query(self, with_clause='', fields={}, groupby='', from_clause=''):
        fields['mk_instance_id'] = ", s.mk_instance_id as mk_instance_id"
        fields['marketplace_type'] = ", mk.marketplace as marketplace_type"
        fields['delivery_amount'] = ", sum((CASE WHEN l.is_delivery THEN l.price_total ELSE 0.0 END)) AS delivery_amount"
        fields['product_type'] = ", t.type as product_type"

        from_clause += """
            left join mk_instance mk on (s.mk_instance_id = mk.id)
        """

        groupby += """
            , s.mk_instance_id
            , mk.marketplace
            , t.type
        """

        return super(SaleReport, self)._query(with_clause, fields, groupby, from_clause)

    def redirect_to_mk_sale_report(self):
        odoo_version = odoo.service.common.exp_version()
        if odoo_version['server_version'] == '15.0+e':
            return self.env.ref('base_marketplace.marketplace_ent_sale_report_action_dashboard').read()[0]
        else:
            return self.env.ref('base_marketplace.marketplace_comm_sale_report_action_dashboard').read()[0]
