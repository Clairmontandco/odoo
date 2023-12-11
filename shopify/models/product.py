from odoo import models, _
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def shopify_export_product_limitation(self):
        """
        Checking for maximum product export limit to prevent user's process.

        :return: True if selected product isn't more than limit.
        :rtype: bool
        :raise UserError:
                * if selected product more than given limit.
        """
        max_limit = 80
        if self and len(self) > max_limit:
            raise UserError(_("System won't allows to export more then 80 products at a time. Please select only 80 product for export."))
        return True

    def shopify_prepare_vals_for_create_listing(self, mk_instance_id):
        vals = {}
        if self.type == 'consu':
            vals.update({'inventory_management': 'dont_track'})
        return vals


class ProductProduct(models.Model):
    _inherit = "product.product"

    def shopify_prepare_vals_for_update_listing_item(self, mk_instance_id):
        return {'barcode': self.barcode}

    def convert_weight_uom_for_shopify(self):
        default_uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        if default_uom_id == self.env.ref('uom.product_uom_lb'):
            return 'lb'
        elif default_uom_id == self.env.ref('uom.product_uom_oz'):
            return 'oz'
        elif default_uom_id == self.env.ref('uom.product_uom_kgm'):
            return 'kg'
        elif default_uom_id == self.env.ref('uom.product_uom_gram'):
            return 'g'
        raise UserError(_("Unsupported Weight UOM for Shopify. Supported weight UOM: g, kg, oz, and lb"))

    def shopify_prepare_vals_for_create_listing_item(self, mk_instance_id):
        vals = {'weight_unit': self.convert_weight_uom_for_shopify()}
        if self.type == 'consu':
            vals.update({'inventory_management': 'dont_track'})
        if self.barcode:
            vals.update({'barcode': self.barcode})
        return vals