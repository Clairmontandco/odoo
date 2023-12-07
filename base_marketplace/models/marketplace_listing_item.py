import ast
import json
from lxml import etree
from odoo.osv import expression
from odoo import models, fields, api, _

EXPORT_QTY_TYPE = [('fix', 'Fix'), ('percentage', 'Percentage')]


class MkListingItem(models.Model):
    _name = "mk.listing.item"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Marketplace Listing Items'

    def _compute_sales_price_with_currency(self):
        date = fields.Datetime.now()
        for record in self:
            instance_id = record.mk_instance_id or record.mk_listing_id.mk_instance_id
            pricelist_item_id = self.env['product.pricelist.item'].search([('pricelist_id', '=', instance_id.pricelist_id.id), ('product_id', '=', record.product_id.id), ('active', '=', True), '|', ('date_start', '=', False),
                                                                           ('date_start', '<=', date), '|', ('date_end', '=', False), ('date_end', '>=', date)], order='id', limit=1)
            record.sale_price = pricelist_item_id.fixed_price or False
            record.currency_id = pricelist_item_id.currency_id.id or False

    name = fields.Char('Name', required=True)
    sequence = fields.Integer(help="Determine the display order", default=10)
    mk_id = fields.Char("Marketplace Identification", copy=False)
    product_id = fields.Many2one('product.product', string='Product', ondelete='cascade')
    mk_listing_id = fields.Many2one('mk.listing', "Listing", ondelete="cascade")
    mk_instance_id = fields.Many2one('mk.instance', "Instance", ondelete='cascade')
    marketplace = fields.Selection(related="mk_instance_id.marketplace", string='Marketplace')
    default_code = fields.Char('Internal Reference')
    barcode = fields.Char('Barcode', copy=False, help="International Article Number used for product identification.")
    item_create_date = fields.Datetime("Creation Date", readonly=True, index=True)
    item_update_date = fields.Datetime("Updated On", readonly=True)
    is_listed = fields.Boolean("Listed?", copy=False)
    export_qty_type = fields.Selection(EXPORT_QTY_TYPE, string="Export Qty Type")
    export_qty_value = fields.Float("Export Qty Value")
    image_ids = fields.Many2many('mk.listing.image', 'mk_listing_image_listing_rel', 'listing_item_id', 'mk_listing_image_id', string="Images")
    sale_price = fields.Monetary(compute="_compute_sales_price_with_currency", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', compute="_compute_sales_price_with_currency")

    @api.depends('default_code', 'name')
    def name_get(self):
        res = []
        for record in self:
            name = record.name
            if record.default_code:
                name = "[%s] %s" % (record.default_code, name)
                res.append((record.id, name))
        return res

    def get_fields_for_hide(self):
        marketplace_list = self.env['mk.instance'].get_all_marketplace()
        field_dict = {}
        for marketplace in marketplace_list:
            if hasattr(self, '%s_hide_fields' % marketplace):
                field_list = getattr(self, '%s_hide_fields' % marketplace)()
                field_dict.update({marketplace: field_list})
        return field_dict

    def get_page_for_hide(self):
        marketplace_list = self.env['mk.instance'].get_all_marketplace()
        page_dict = {}
        for marketplace in marketplace_list:
            if hasattr(self, '%s_hide_page' % marketplace):
                page_list = getattr(self, '%s_hide_page' % marketplace)()
                page_dict.update({marketplace: page_list})
        return page_dict

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', **options):
        ret_val = super(MkListingItem, self).fields_view_get(view_id=view_id, view_type=view_type, **options)
        need_to_hide_field_dict = self.get_fields_for_hide()
        doc = etree.XML(ret_val['arch'])
        if view_type == 'form':
            need_to_hide_page_list = self.get_page_for_hide()
            for marketplace, page_list in need_to_hide_page_list.items():
                for page in page_list:
                    for node in doc.xpath("//page[@name='%s']" % page):
                        existing_domain, new_domain = [], []
                        if not node.get("modifiers"):
                            node.set("modifiers", json.dumps({'invisible': [('marketplace', '=', marketplace)]}))
                            continue
                        modifiers = json.loads(node.get("modifiers"))
                        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
                            if not existing_domain:
                                existing_domain = modifiers['invisible']
                            if not new_domain:
                                new_domain = [('marketplace', '=', marketplace)]
                            else:
                                new_domain = expression.OR([new_domain, [('marketplace', '=', marketplace)]])
                        else:
                            modifiers['invisible'] = [('marketplace', '=', marketplace)]
                        node.set("modifiers", json.dumps(modifiers))
                        if existing_domain and new_domain:
                            node.set("modifiers", json.dumps({'invisible': expression.OR([existing_domain, new_domain])}))
            for marketplace, instance_field_list in need_to_hide_field_dict.items():
                for field in instance_field_list:
                    for node in doc.xpath("//field[@name='%s']" % field):
                        existing_domain, new_domain = [], []
                        modifiers = node.get("modifiers") and json.loads(node.get("modifiers")) or {}
                        if 'invisible' in modifiers and isinstance(modifiers['invisible'], list):
                            if not existing_domain:
                                existing_domain = modifiers['invisible']
                            if not new_domain:
                                new_domain = [('marketplace', '=', marketplace)]
                            else:
                                new_domain = expression.OR([new_domain, [('marketplace', '=', marketplace)]])
                        else:
                            modifiers['invisible'] = [('marketplace', '=', marketplace)]
                        node.set("modifiers", json.dumps(modifiers))
                        if existing_domain and new_domain:
                            force_modifiers = {}
                            force_modifiers['invisible'] = expression.OR([existing_domain, new_domain])
                            node.set("modifiers", json.dumps(force_modifiers))
        ret_val['arch'] = etree.tostring(doc, encoding='unicode')
        return ret_val

    def create_or_update_pricelist_item(self, variant_price, update_product_price=False, reversal_convert=False, skip_conversion=False):
        self.ensure_one()
        instance_id = self.mk_instance_id or self.mk_listing_id.mk_instance_id
        pricelist_currency = instance_id.pricelist_id.currency_id
        company_currency = self.product_id.product_tmpl_id.currency_id
        if pricelist_currency != company_currency:
            if reversal_convert:
                variant_price = company_currency._convert(variant_price, pricelist_currency, instance_id.company_id, fields.Date.today())
            else:
                variant_price = pricelist_currency._convert(variant_price, company_currency, instance_id.company_id, fields.Date.today())
        pricelist_item_id = self.env['product.pricelist.item'].search([('pricelist_id', '=', instance_id.pricelist_id.id), ('product_id', '=', self.product_id.id)], limit=1)
        if not pricelist_item_id:
            instance_id.pricelist_id.write({'item_ids': [(0, 0, {
                'applied_on': '0_product_variant',
                'product_id': self.product_id.id,
                'product_tmpl_id': self.product_id.product_tmpl_id.id,
                'compute_price': 'fixed',
                'fixed_price': variant_price
            })]})
        elif pricelist_item_id and update_product_price:
            pricelist_item_id.write({'compute_price': 'fixed',
                                     'fixed_price': variant_price})
        return True

    def action_change_listing_item_price(self):
        action = self.env.ref('base_marketplace.action_product_pricelistitem_mk').read()[0]
        custom_view_id = self.env.ref('base_marketplace.mk_product_pricelist_item_advanced_tree_view') if self.env.user.has_group('product.group_sale_pricelist') else False
        if hasattr(self, '%s_action_change_price_view' % self.mk_instance_id.marketplace):
            custom_view_id = getattr(self, '%s_action_change_price_view' % self.mk_instance_id.marketplace)()
        context = self._context.copy()
        if 'context' in action and type(action['context']) == str:
            context.update(ast.literal_eval(action['context']))
        else:
            context.update(action.get('context', {}))
        action['context'] = context
        action['context'].update({
            'default_product_tmpl_id': self.product_id.product_tmpl_id.id,
            'default_product_id': self.product_id.id,
            'default_applied_on': '0_product_variant',
            'default_compute_price': 'fixed',
            'default_pricelist_id': self.mk_instance_id.pricelist_id.id,
            'search_default_Variant Rule': 1,
        })
        if custom_view_id:
            views = [(custom_view_id.id, 'tree')]
            if self.env.user.has_group('product.group_sale_pricelist'):
                views.append((self.env.ref('product.product_pricelist_item_form_view').id, 'form'))
            action['views'] = views
        instance_id = self.mk_instance_id or self.mk_listing_id.mk_instance_id
        action['domain'] = [('pricelist_id', '=', instance_id.pricelist_id.id), ('product_id', '=', self.product_id.id)]
        return action
