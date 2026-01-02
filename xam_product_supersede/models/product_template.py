# -*- coding: utf-8 -*-
from __future__ import annotations

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Editable from template, stored on the single variant (product_variant_id)
    supersede_ids = fields.One2many(
        related="product_variant_id.variant_supersede_ids",
        readonly=False,
        string="Supersession Relationships",
    )

    superseded_by_id = fields.Many2one(
        related="product_variant_id.superseded_by_id",
        readonly=True,
        string="Superseded By",
    )
    supersedes_ids = fields.Many2many(
        related="product_variant_id.supersedes_ids",
        readonly=True,
        string="Supersedes",
    )

    def action_replace_in_quotations(self):
        """Convenience pass-through for templates (single-variant expected)."""
        self.ensure_one()
        return self.product_variant_id.action_replace_in_quotations()


class ProductProduct(models.Model):
    _inherit = "product.product"

    variant_supersede_ids = fields.One2many(
        "product.supersede",
        "product_id",
        string="Variant Supersessions",
        copy=True,
    )

    superseded_by_id = fields.Many2one(
        "product.product",
        compute="_compute_supersession_primary",
        string="Superseded By",
        store=False,
    )
    supersedes_ids = fields.Many2many(
        "product.product",
        compute="_compute_supersession_primary",
        string="Supersedes",
        store=False,
    )

    @api.depends("variant_supersede_ids.relationship_type", "variant_supersede_ids.active",
                 "variant_supersede_ids.effective_date", "variant_supersede_ids.expiration_date",
                 "variant_supersede_ids.related_product_id", "variant_supersede_ids.sequence")
    def _compute_supersession_primary(self):
        today = fields.Date.context_today(self)
        for product in self:
            rels = product.variant_supersede_ids.filtered(lambda r: r.active)
            # currently effective
            rels = rels.filtered(lambda r: (not r.effective_date or r.effective_date <= today) and
                                           (not r.expiration_date or r.expiration_date >= today))
            superseded_by = rels.filtered(lambda r: r.relationship_type == "superseded_by").sorted("sequence")
            supersedes = rels.filtered(lambda r: r.relationship_type == "supersedes").sorted("sequence")

            product.superseded_by_id = superseded_by[:1].related_product_id if superseded_by else False
            product.supersedes_ids = supersedes.mapped("related_product_id")

    # ---------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------
    def get_replacement_product(self):
        """Return the best replacement product (superseded_by) if any."""
        self.ensure_one()
        return self.superseded_by_id

    # ---------------------------------------------------------------------
    # Business actions (optional integrations guarded by model existence)
    # ---------------------------------------------------------------------
    def action_replace_in_quotations(self):
        """
        Replace this product with its replacement in draft/sent quotations (Sale module installed).
        Safe to call even if Sale isn't installed.
        """
        self.ensure_one()
        replacement = self.get_replacement_product()
        if not replacement:
            raise UserError(_("No replacement product is defined for %s.") % self.display_name)

        if "sale.order.line" not in self.env:
            raise UserError(_("Sale app is not installed."))

        sol = self.env["sale.order.line"].search([
            ("product_id", "=", self.id),
            ("order_id.state", "in", ["draft", "sent"]),
        ])
        if not sol:
            raise UserError(_("No draft/sent quotations found for this product."))

        # Replace product_id; Odoo will recompute description/uom/price via onchange in UI,
        # but here we preserve quantities and re-trigger recompute with compute methods.
        sol.write({"product_id": replacement.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Updated Quotation Lines"),
            "res_model": "sale.order.line",
            "view_mode": "tree,form",
            "domain": [("id", "in", sol.ids)],
        }
