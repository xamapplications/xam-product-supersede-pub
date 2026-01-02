# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict, deque

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductSupersede(models.Model):
    """
    Product supersession relationships between product.product records.

    Relationship semantics:
      - supersedes:         product_id supersedes related_product_id
      - superseded_by:      product_id is superseded by related_product_id
      - interchangeable:    product_id can be used interchangeably with related_product_id

    This model auto-creates/keeps a reverse record for the pair:
      - supersedes <-> superseded_by
      - interchangeable <-> interchangeable
    """
    _name = "product.supersede"
    _description = "Product Supersession"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"
    _rec_name = "display_name"

    product_id = fields.Many2one(
        "product.product",
        string="Main Product",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    related_product_id = fields.Many2one(
        "product.product",
        string="Related Product",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    relationship_type = fields.Selection(
        [
            ("supersedes", "Supersedes"),
            ("superseded_by", "Superseded By"),
            ("interchangeable", "Interchangeable"),
        ],
        string="Relationship Type",
        default="supersedes",
        required=True,
        index=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="product_id.company_id",
        store=True,
        readonly=True,
    )

    sequence = fields.Integer(default=10, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    effective_date = fields.Date(string="Effective Date", default=fields.Date.today, tracking=True)
    expiration_date = fields.Date(string="Expiration Date", tracking=True)

    notes = fields.Text(string="Notes", tracking=True)

    display_name = fields.Char(string="Display Name", compute="_compute_display_name", store=True)
    is_current = fields.Boolean(string="Is Current", compute="_compute_is_current", store=True)
    state = fields.Selection(
        [
            ("future", "Future"),
            ("active", "Active"),
            ("expired", "Expired"),
        ],
        compute="_compute_state",
        store=True,
        readonly=True,
    )

    _sql_constraints = [
        (
            "product_related_diff",
            "CHECK(product_id != related_product_id)",
            "Main Product and Related Product must be different.",
        ),
        (
            "uniq_relation_pair_company",
            "UNIQUE(product_id, related_product_id, relationship_type, company_id)",
            "This relationship already exists for the same products and company.",
        ),
    ]

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------
    @api.depends("product_id", "related_product_id", "relationship_type")
    def _compute_display_name(self):
        label = dict(self._fields["relationship_type"].selection)
        for rec in self:
            if rec.product_id and rec.related_product_id:
                rec.display_name = "%s %s %s" % (
                    rec.product_id.display_name,
                    label.get(rec.relationship_type, rec.relationship_type),
                    rec.related_product_id.display_name,
                )
            else:
                rec.display_name = _("Relationship")

    @api.depends("effective_date", "expiration_date", "active")
    def _compute_is_current(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.active:
                rec.is_current = False
                continue
            if rec.effective_date and rec.effective_date > today:
                rec.is_current = False
                continue
            rec.is_current = (not rec.expiration_date) or (rec.expiration_date >= today)

    @api.depends("effective_date", "expiration_date", "active")
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.active:
                rec.state = "expired"
                continue
            if rec.effective_date and rec.effective_date > today:
                rec.state = "future"
            elif rec.expiration_date and rec.expiration_date < today:
                rec.state = "expired"
            else:
                rec.state = "active"

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _reverse_relationship_type(self, relationship_type: str) -> str:
        if relationship_type == "supersedes":
            return "superseded_by"
        if relationship_type == "superseded_by":
            return "supersedes"
        return "interchangeable"

    def _pair_domain(self, p1_id: int, p2_id: int):
        return [("product_id", "=", p1_id), ("related_product_id", "=", p2_id)]

    def _build_supersedes_graph(self, company_id: int | None):
        """
        Build directed graph edges for supersedes relationships only:
            A --supersedes--> B
        Returns: dict[int, set[int]]
        """
        dom = [("relationship_type", "=", "supersedes"), ("active", "=", True)]
        if company_id:
            dom.append(("company_id", "=", company_id))
        rels = self.search(dom).read(["product_id", "related_product_id"])
        graph = defaultdict(set)
        for r in rels:
            if r.get("product_id") and r.get("related_product_id"):
                graph[r["product_id"][0]].add(r["related_product_id"][0])
        return graph

    def _check_no_cycle(self):
        """
        Prevent cycles in directed supersedes relationships.
        Applied when relationship_type in (supersedes, superseded_by) because they map to supersedes edges.
        """
        # Only check for records that could introduce/affect directed supersedes edges.
        candidates = self.filtered(lambda r: r.relationship_type in ("supersedes", "superseded_by"))
        if not candidates:
            return

        # Check per-company for correctness and performance.
        for company in candidates.mapped("company_id"):
            company_recs = candidates.filtered(lambda r: r.company_id == company)

            graph = self._build_supersedes_graph(company.id if company else None)

            # Apply candidate edges as if they were supersedes
            for rec in company_recs:
                if not (rec.product_id and rec.related_product_id):
                    continue
                if rec.relationship_type == "supersedes":
                    src, dst = rec.product_id.id, rec.related_product_id.id
                else:
                    # superseded_by means: related_product supersedes product
                    src, dst = rec.related_product_id.id, rec.product_id.id

                # add temporary edge
                graph[src].add(dst)

                # Detect cycle: if src reachable from dst then cycle exists.
                if self._is_reachable(graph, dst, src):
                    raise ValidationError(
                        _("Supersession cycle detected: this relationship would create a loop.")
                    )

    @staticmethod
    def _is_reachable(graph, start, target) -> bool:
        if start == target:
            return True
        seen = set()
        q = deque([start])
        while q:
            node = q.popleft()
            if node in seen:
                continue
            seen.add(node)
            for nxt in graph.get(node, ()):
                if nxt == target:
                    return True
                if nxt not in seen:
                    q.append(nxt)
        return False

    def _ensure_reverse_links(self):
        """
        Ensure reverse relationship exists and is synced.
        """
        if self.env.context.get("skip_reverse_update"):
            return

        # Batch search existing reverse records
        pairs = []
        for rec in self:
            if rec.product_id and rec.related_product_id:
                pairs.append((rec.related_product_id.id, rec.product_id.id))
        if not pairs:
            return

        # Search all possible reverse records in one query
        dom = ["|"] * (len(pairs) - 1) if len(pairs) > 1 else []
        for p1, p2 in pairs:
            dom += [("product_id", "=", p1), ("related_product_id", "=", p2)]
        existing = self.search(dom)
        existing_map = {(r.product_id.id, r.related_product_id.id): r for r in existing}

        to_create = []
        for rec in self:
            if not (rec.product_id and rec.related_product_id):
                continue

            reverse_type = rec._reverse_relationship_type(rec.relationship_type)
            key = (rec.related_product_id.id, rec.product_id.id)
            reverse = existing_map.get(key)

            vals_to_sync = {
                "relationship_type": reverse_type,
                "active": rec.active,
                "effective_date": rec.effective_date,
                "expiration_date": rec.expiration_date,
                "sequence": rec.sequence,
                "notes": rec.notes,
            }

            if reverse:
                reverse.with_context(skip_reverse_update=True).write(vals_to_sync)
            else:
                to_create.append(
                    {
                        "product_id": rec.related_product_id.id,
                        "related_product_id": rec.product_id.id,
                        **vals_to_sync,
                    }
                )

        if to_create:
            self.with_context(skip_reverse_update=True).create(to_create)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------
    @api.constrains("effective_date", "expiration_date")
    def _check_dates(self):
        for rec in self:
            if rec.effective_date and rec.expiration_date and rec.expiration_date < rec.effective_date:
                raise ValidationError(_("Expiration Date must be on or after Effective Date."))

    @api.constrains("product_id", "related_product_id", "relationship_type", "active")
    def _check_cycles_and_reverse(self):
        # Cycle check first
        self._check_no_cycle()

    # -------------------------------------------------------------------------
    # ORM overrides
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_reverse_links()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ensure_reverse_links()
        return res

    def unlink(self):
        if self.env.context.get("skip_reverse_update"):
            return super().unlink()

        # delete reverse records too (best-effort)
        for rec in self:
            reverse = self.search(
                [
                    ("product_id", "=", rec.related_product_id.id),
                    ("related_product_id", "=", rec.product_id.id),
                ],
                limit=1,
            )
            if reverse:
                reverse.with_context(skip_reverse_update=True).unlink()
        return super().unlink()
