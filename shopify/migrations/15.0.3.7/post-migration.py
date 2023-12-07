# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute("""
        UPDATE mk_listing
        SET shopify_published_scope =
                CASE WHEN is_published = true
            THEN 'web'
            ELSE 'unpublished'
        END;
    """)
    cr.execute("""UPDATE mk_instance SET import_order_after_date = shopify_import_after_order""")
