"""DuckDB 1.5.5 native AST -> closed recursive visitor -> newly emitted SQL.

No binder, EXPLAIN, original SQL execution, filesystem or extension functions.
Unknown nodes/fields fail closed. Parsing calls only json_serialize_sql(?) on a
fresh in-memory connection with external access and extension loading disabled.
"""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import re

from . import CONTRACT_VERSION
from .contracts import (
    Decision, RelationState, ResolvedRelation, SecurityDecision, TypedParameter,
    ValidatedExploratoryQuery,
)
from .synthetic import CATALOG


class Rejected(ValueError):
    def __init__(self, reason, decision=Decision.INVALID_QUERY):
        self.reason, self.decision = reason, decision
        super().__init__(reason)


def require(condition, reason="unsupported_ast"):
    if not condition:
        raise Rejected(reason)


def fields(node, names):
    require(isinstance(node, dict) and set(node) == set(names.split()), "unknown_ast_fields")


def identifier(name):
    require(isinstance(name, str) and bool(re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name)),
            "unsupported_identifier")
    return '"' + name + '"'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def context_digest(context):
    return digest(asdict(context) | {"permissions": sorted(context.permissions)})


def authorize(context):
    # Opt-in issued catalogs are identity-sealed, not accepted by value equality.
    from .authorized_foundation import binding_for, authorize_issued
    if binding_for(context) is not None:
        authorize_issued(context)
        return
    # Only sealed catalogs from trusted composition, never model-owned metadata.
    catalog = CATALOG
    if context.catalog != CATALOG:
        import os
        from .foundation import CATALOG as FOUNDATION_CATALOG
        if context.identity != f"supervised-local-uid:{os.getuid()}":
            raise Rejected("unauthorized_context", Decision.DENY)
        from .adaptive_sources import CATALOG as ADAPTIVE_CATALOG
        from .ask_sources import CATALOG as ASK_CATALOG
        catalog = (ASK_CATALOG if context.catalog == ASK_CATALOG else
                   ADAPTIVE_CATALOG if context.catalog == ADAPTIVE_CATALOG else FOUNDATION_CATALOG)
    if (context.version != CONTRACT_VERSION or context.environment != "dev"
            or context.catalog != catalog or context.organization != catalog.organization
            or context.workspace != catalog.workspace or context.publication != catalog.publication
            or context.snapshot != catalog.snapshot or not context.identity or not context.investigation_id
            or not set(context.sources) <= {t.name for t in catalog.tables}):
        raise Rejected("unauthorized_context", Decision.DENY)


class Visitor:
    def __init__(self, proposal, context):
        self.proposal, self.context = proposal, context
        from .authorized_foundation import binding_for
        self.authorized_catalog = binding_for(context) is not None
        self.budget = context.effective_budget.intersect(proposal.requested_budget)
        self.sources, self.columns, self.functions = set(), set(), set()
        self.parameters, self.used_parameters, self.relations = [], set(), []
        self.input_parameters = {p.name: p for p in proposal.parameters}
        require(len(self.input_parameters) == len(proposal.parameters), "duplicate_parameter")
        self.visits = 0

    def parameter(self, value, sql_type):
        # DuckDB compares parameter identities when binding repeated GROUP BY
        # expressions. Equal typed literals must retain equal identities, not
        # merely equal runtime values. No literal is interpolated into SQL.
        for existing in self.parameters:
            if (existing.sql_type == sql_type and type(existing.value) is type(value)
                    and existing.value == value):
                return f"CAST(${existing.name} AS {sql_type})"
        name = f"p{len(self.parameters)}"
        param = TypedParameter(name, sql_type, value)
        self.parameters.append(param)
        return f"CAST(${name} AS {sql_type})"

    def typed(self, param):
        value, typ = param.value, param.sql_type
        require((typ == "INTEGER" and type(value) is int and -(2**31) <= value < 2**31)
                or (typ == "VARCHAR" and type(value) is str and len(value) <= 1024)
                or (typ == "BOOLEAN" and type(value) is bool)
                or (typ == "DECIMAL(18,2)" and isinstance(value, Decimal)
                    and value.is_finite() and abs(value) < Decimal("1e16")
                    and value.as_tuple().exponent >= -2), "invalid_parameter_type")
        return self.parameter(value, typ)

    def resolve(self, expr, scope):
        names = expr["column_names"]
        require(1 <= len(names) <= 2, "unknown_column")
        for name in names:
            identifier(name)
        if len(names) == 2:
            alias, col = names
            require(alias in scope and col in scope[alias], "unknown_column")
        else:
            col = names[0]
            matches = [alias for alias, cols in scope.items() if col in cols]
            require(len(matches) == 1, "unknown_or_ambiguous_column")
            alias = matches[0]
        lineage = scope[alias][col]
        if lineage:
            self.columns.add(lineage)
        return f"{identifier(alias)}.{identifier(col)}", lineage

    def expr(self, node, scope, depth=0):
        self.visits += 1
        require(depth <= 20 and self.visits <= 1000, "ast_budget")
        require(isinstance(node, dict) and {"class", "type", "alias", "query_location"} <= set(node))
        cls, typ = node["class"], node["type"]
        common = "class type alias query_location "
        if node["alias"]:
            identifier(node["alias"])
        child = lambda n: self.expr(n, scope, depth + 1)
        if cls == "COLUMN_REF":
            fields(node, common + "column_names")
            require(typ == "COLUMN_REF")
            return self.resolve(node, scope)[0]
        if cls == "CONSTANT":
            fields(node, common + "value")
            require(typ == "VALUE_CONSTANT")
            val = node["value"]
            require(set(val) <= {"type", "is_null", "value"})
            fields(val["type"], "id type_info")
            require(val["type"]["type_info"] is None, "unsupported_literal_type")
            if val["is_null"]:
                return "NULL"
            require(val["type"]["id"] in {"INTEGER", "VARCHAR", "BOOLEAN"}, "unsupported_literal_type")
            return self.typed(TypedParameter("", val["type"]["id"], val["value"]))
        if cls == "PARAMETER":
            fields(node, common + "identifier")
            require(typ == "VALUE_PARAMETER")
            name = node["identifier"]
            identifier(name)
            require(name in self.input_parameters, "missing_parameter")
            self.used_parameters.add(name)
            return self.typed(self.input_parameters[name])
        if cls == "FUNCTION":
            fields(node, common + "function_name schema children filter order_bys distinct is_operator export_state catalog")
            require(typ == "FUNCTION" and not any(node[k] for k in ("schema", "catalog", "export_state", "filter")))
            require(node["order_bys"] == {"type": "ORDER_MODIFIER", "orders": []})
            fn, args = node["function_name"], node["children"]
            arithmetic = {"+", "-", "*", "/", "%"}
            functions = {"count", "count_star", "sum", "min", "max", "avg", "abs", "round", "lower", "upper", "length"}
            # Narrow pure-string discovery needed by open-question DEV only.
            # Historical/synthetic and runtime catalogs keep their old subset.
            if self.context.catalog.dataset == 'telchi_foundation_direct_ask_dev_v1':
                functions.add('contains')
            require(fn in functions | arithmetic, "unauthorized_function")
            require(node["is_operator"] == (fn in arithmetic))
            if fn in arithmetic:
                require(not node["distinct"] and (len(args) == 2 or (fn in {"+", "-"} and len(args) == 1)))
                parts = [child(a) for a in args]
                return "(" + (f" {fn} ".join(parts) if len(parts) == 2 else fn + parts[0]) + ")"
            self.functions.add(fn)
            require(len(args) == (0 if fn == "count_star" else 2 if fn == "contains" else 1)
                    and (not node["distinct"] or fn in {"count", "sum", "avg"}), "unsupported_function_arity")
            if fn == "count_star":
                require(not node["distinct"])
                return "COUNT(*)"
            return fn.upper() + "(" + ("DISTINCT " if node["distinct"] else "") + ', '.join(child(a) for a in args) + ")"
        if cls == "COMPARISON":
            fields(node, common + "left right")
            ops = {"COMPARE_EQUAL": "=", "COMPARE_NOTEQUAL": "<>", "COMPARE_LESSTHAN": "<",
                   "COMPARE_GREATERTHAN": ">", "COMPARE_LESSTHANOREQUALTO": "<=",
                   "COMPARE_GREATERTHANOREQUALTO": ">=", "COMPARE_NOT_DISTINCT_FROM": "IS NOT DISTINCT FROM"}
            require(typ in ops, "unsupported_comparison")
            return f"({child(node['left'])} {ops[typ]} {child(node['right'])})"
        if cls in {"CONJUNCTION", "OPERATOR"}:
            fields(node, common + "children")
            args = node["children"]
            parts = [child(a) for a in args]
            if cls == "CONJUNCTION":
                require(typ in {"CONJUNCTION_AND", "CONJUNCTION_OR"} and len(args) >= 2)
                return "(" + (" AND " if typ == "CONJUNCTION_AND" else " OR ").join(parts) + ")"
            if typ in {"OPERATOR_IS_NULL", "OPERATOR_IS_NOT_NULL", "OPERATOR_NOT"}:
                require(len(parts) == 1)
                return (f"(NOT {parts[0]})" if typ == "OPERATOR_NOT" else
                        f"({parts[0]} IS {'NOT ' if typ == 'OPERATOR_IS_NOT_NULL' else ''}NULL)")
            if typ == "OPERATOR_COALESCE":
                require(2 <= len(parts) <= 8)
                return "COALESCE(" + ", ".join(parts) + ")"
            if typ in {"COMPARE_IN", "COMPARE_NOT_IN"}:
                require(2 <= len(parts) <= 32)
                return f"({parts[0]} {'NOT ' if typ == 'COMPARE_NOT_IN' else ''}IN ({', '.join(parts[1:])}))"
            raise Rejected("unsupported_operator")
        if cls == "CASE":
            fields(node, common + "case_checks else_expr")
            require(typ == "CASE_EXPR" and 1 <= len(node["case_checks"]) <= 8)
            parts = []
            for check in node["case_checks"]:
                fields(check, "when_expr then_expr")
                parts.append(f"WHEN {child(check['when_expr'])} THEN {child(check['then_expr'])}")
            return "(CASE " + " ".join(parts) + " ELSE " + child(node["else_expr"]) + " END)"
        if cls == "BETWEEN":
            fields(node, common + "input lower upper")
            require(typ == "COMPARE_BETWEEN")
            return f"({child(node['input'])} BETWEEN {child(node['lower'])} AND {child(node['upper'])})"
        # Scalar/correlated subqueries, windows, casts, stars, lambdas, lists,
        # macros and unknown constructs are explicitly outside this V1 subset.
        raise Rejected("unsupported_expression")

    def from_table(self, node, ctes, depth):
        require(depth <= 12, "relation_depth")
        base = "type alias sample query_location "
        require(node.get("sample") is None, "sampling_not_supported")
        typ = node.get("type")
        if typ == "BASE_TABLE":
            fields(node, base + "schema_name table_name column_name_alias catalog_name at_clause")
            require(not any(node[k] for k in ("schema_name", "catalog_name", "column_name_alias", "at_clause")), "physical_reference_denied")
            name = node["table_name"]
            identifier(name)
            alias = node["alias"] or name
            identifier(alias)
            if name in ctes:
                cols, bound = ctes[name]
            else:
                tables = {t.name: t for t in self.context.catalog.tables}
                if name not in tables or name not in self.context.sources:
                    raise Rejected("source_not_authorized", Decision.DENY)
                table = tables[name]
                if table.permission not in self.context.permissions:
                    raise Rejected("permission_denied", Decision.DENY)
                require(name in self.proposal.requested_sources, "undeclared_source")
                self.sources.add(name)
                cols, bound = {c.name: (name, c.name) for c in table.columns}, table.max_rows
            return f"{identifier(name)} AS {identifier(alias)}", {alias: cols}, bound
        if typ == "SUBQUERY":
            fields(node, base + "subquery column_name_alias")
            require(not node["column_name_alias"] and bool(node["alias"]), "subquery_alias_required")
            alias = node["alias"]
            identifier(alias)
            sql, cols, bound = self.query_wrapper(node["subquery"], ctes, depth + 1)
            return f"({sql}) AS {identifier(alias)}", {alias: cols}, bound
        if typ == "JOIN":
            fields(node, base + "left right condition join_type ref_type using_columns delim_flipped duplicate_eliminated_columns")
            require(not any(node[k] for k in ("alias", "using_columns", "delim_flipped", "duplicate_eliminated_columns"))
                    and node["ref_type"] == "REGULAR" and node["join_type"] in {"INNER", "LEFT"}, "unsupported_join")
            left, ls, lb = self.from_table(node["left"], ctes, depth + 1)
            right, rs, rb = self.from_table(node["right"], ctes, depth + 1)
            require(not set(ls) & set(rs), "duplicate_alias")
            bound = lb * max(1, rb)
            if bound > self.budget.max_join_pairs:
                raise Rejected("join_pair_budget", Decision.RESOURCE_BLOCKED)
            scope = ls | rs
            condition = node["condition"]
            # Every join must have a mandatory column equality across its sides.
            # Equality hidden under OR, tautologies or same-side references fails.
            def equalities(n):
                if isinstance(n, dict) and n.get("class") == "CONJUNCTION" and n.get("type") == "CONJUNCTION_AND":
                    return [e for x in n["children"] for e in equalities(x)]
                if isinstance(n, dict) and n.get("class") == "COMPARISON" and n.get("type") == "COMPARE_EQUAL":
                    a, b = n["left"], n["right"]
                    if a.get("class") == b.get("class") == "COLUMN_REF":
                        sa, la = self.resolve(a, scope)
                        sb, ra = self.resolve(b, scope)
                        aa, bb = sa.split(".")[0], sb.split(".")[0]
                        if ((aa in {identifier(x) for x in ls} and bb in {identifier(x) for x in rs})
                                or (bb in {identifier(x) for x in ls} and aa in {identifier(x) for x in rs})):
                            return [(la, ra)]
                return []
            keys = equalities(condition)
            require(keys, "cartesian_or_uncontrolled_join")
            for a, b in keys:
                if a is None or b is None:
                    self.relations.append(ResolvedRelation(a or ("derived", "unknown"), b or ("derived", "unknown"), RelationState.INSUFFICIENT))
                    continue
                def matches(r):
                    return {a, b} == {(r.left_table, r.left_column), (r.right_table, r.right_column)}
                known = any(matches(r) for r in self.context.catalog.known_relations)
                proposed = any(matches(r) for r in self.proposal.candidate_relations)
                require(known or proposed, "undeclared_candidate_relation")
                self.relations.append(ResolvedRelation(a, b, RelationState.ACCREDITED if known else RelationState.INVESTIGATIVE))
            return f"({left} {node['join_type']} JOIN {right} ON {self.expr(condition, scope)})", scope, bound
        raise Rejected("unsupported_source_node")

    def query_wrapper(self, wrapper, ctes, depth):
        fields(wrapper, "node named_param_map")
        # Parameter map contains only parser-generated indexes, never authority.
        for entry in wrapper["named_param_map"]:
            fields(entry, "key value")
            identifier(entry["key"])
            require(type(entry["value"]) is int and entry["value"] > 0)
        return self.query(wrapper["node"], ctes, depth)

    def query(self, node, inherited_ctes, depth=0):
        require(depth <= 8, "query_depth")
        fields(node, "type modifiers cte_map select_list from_table where_clause group_expressions group_sets aggregate_handling having sample qualify")
        require(node["type"] == "SELECT_NODE", "select_only")
        require(node["sample"] is None and node["qualify"] is None
                and node["aggregate_handling"] == "STANDARD_HANDLING", "unsupported_select")
        ctes, with_parts = dict(inherited_ctes), []
        fields(node["cte_map"], "map")
        require(len(node["cte_map"]["map"]) <= 8, "cte_budget")
        for entry in node["cte_map"]["map"]:
            fields(entry, "key value")
            name, val = entry["key"], entry["value"]
            identifier(name)
            require(name not in ctes and name not in {t.name for t in self.context.catalog.tables}, "cte_shadowing")
            fields(val, "aliases query materialized key_targets")
            require(not val["aliases"] and not val["key_targets"]
                    and val["materialized"] == "CTE_MATERIALIZE_DEFAULT", "unsupported_cte")
            sql, cols, bound = self.query_wrapper(val["query"], ctes, depth + 1)
            ctes[name] = (cols, bound)
            with_parts.append(f"{identifier(name)} AS ({sql})")
        source, scope, bound = self.from_table(node["from_table"], ctes, depth + 1)
        require(1 <= len(node["select_list"]) <= 32, "projection_budget")
        projections, outputs = [], {}
        for index, expr in enumerate(node["select_list"]):
            sql = self.expr(expr, scope)
            alias = expr["alias"] or (expr["column_names"][-1] if expr["class"] == "COLUMN_REF" else f"expr_{index}")
            identifier(alias)
            require(alias not in outputs, "duplicate_output_column")
            outputs[alias] = self.resolve(expr, scope)[1] if expr["class"] == "COLUMN_REF" else None
            projections.append(sql + " AS " + identifier(alias))
        groups = node["group_expressions"]
        require(node["group_sets"] == ([list(range(len(groups)))] if groups else []), "unsupported_grouping_sets")
        sql = "SELECT " + ", ".join(projections) + " FROM " + source
        if node["where_clause"] is not None:
            sql += " WHERE " + self.expr(node["where_clause"], scope)
        if groups:
            sql += " GROUP BY " + ", ".join(self.expr(g, scope) for g in groups)
        if node["having"] is not None:
            sql += " HAVING " + self.expr(node["having"], scope)
        seen_modifiers = set()
        for mod in node["modifiers"]:
            typ = mod["type"]
            require(typ not in seen_modifiers, "duplicate_modifier")
            seen_modifiers.add(typ)
            if typ == "DISTINCT_MODIFIER":
                fields(mod, "type distinct_on_targets")
                require(not mod["distinct_on_targets"], "distinct_on_unsupported")
                sql = sql.replace("SELECT ", "SELECT DISTINCT ", 1)
            elif typ == "ORDER_MODIFIER":
                fields(mod, "type orders")
                parts = []
                for order in mod["orders"]:
                    fields(order, "type null_order expression")
                    require(order["type"] in {"ASCENDING", "DESCENDING", "ORDER_DEFAULT"})
                    require(order["null_order"] in {"NULLS_FIRST", "NULLS_LAST", "ORDER_DEFAULT"})
                    expr = order["expression"]
                    if expr.get("class") == "COLUMN_REF" and len(expr["column_names"]) == 1 and expr["column_names"][0] in outputs:
                        value = identifier(expr["column_names"][0])
                    else:
                        value = self.expr(expr, scope)
                    direction = "DESC" if order["type"] == "DESCENDING" else "ASC"
                    nulls = {"NULLS_FIRST": " NULLS FIRST", "NULLS_LAST": " NULLS LAST", "ORDER_DEFAULT": ""}[order["null_order"]]
                    parts.append(f"{value} {direction}{nulls}")
                require(parts)
                sql += " ORDER BY " + ", ".join(parts)
            elif typ == "LIMIT_MODIFIER":
                fields(mod, "type limit offset")
                require(mod["offset"] is None and mod["limit"] is not None, "unsupported_offset")
                lim = mod["limit"]
                require(lim.get("class") == "CONSTANT" and type(lim["value"].get("value")) is int
                        and 0 <= lim["value"]["value"] <= self.budget.result_rows, "limit_budget")
                # Walk entire literal too, but use a bounded trusted integer in emitted LIMIT.
                self.expr(lim, scope)
                sql += " LIMIT " + str(lim["value"]["value"])
                if self.authorized_catalog:
                    # Proven output bound for a derived relation/CTE, not a
                    # source-scan estimate or a larger join budget. The join
                    # inside this SELECT was already checked before LIMIT.
                    bound = min(bound, lim["value"]["value"])
            else:
                raise Rejected("unsupported_modifier")
        if with_parts:
            sql = "WITH " + ", ".join(with_parts) + " " + sql
        return sql, outputs, bound


def validate(proposal, context):
    """Return safe decision + immutable candidate; ALLOW does not enable execution."""
    try:
        authorize(context)
        require(proposal.version == CONTRACT_VERSION, "contract_version")
        require(isinstance(proposal.sql, str) and 0 < len(proposal.sql.encode()) <= 8192, "sql_size")
        require(all(isinstance(s, str) and s.strip() and len(s) <= 1024 for s in
                    (proposal.objective, proposal.justification, proposal.expected_grain, proposal.expected_result)), "proposal_metadata")
        require(set(proposal.requested_sources) <= set(context.sources), "requested_source_not_authorized")
        import duckdb
        if duckdb.__version__ != "1.5.5":
            raise Rejected("parser_version_not_accredited", Decision.RESOURCE_BLOCKED)
        with duckdb.connect(":memory:", config={
            "threads": "1", "memory_limit": "64MB", "max_expression_depth": "64",
            "enable_external_access": "false", "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
        }) as connection:
            raw = connection.execute("SELECT json_serialize_sql(?)", [proposal.sql]).fetchone()[0]
        tree = json.loads(raw)
        require(tree.get("error") is False, "parse_error")
        fields(tree, "error statements")
        require(len(tree["statements"]) == 1, "single_statement_required")
        visitor = Visitor(proposal, context)
        generated, _, _ = visitor.query_wrapper(tree["statements"][0], {}, 0)
        require(visitor.used_parameters == set(visitor.input_parameters), "unused_parameter")
        # Parameters used solely to validate LIMIT are harmless but omit unused bindings.
        parameters = tuple(p for p in visitor.parameters if f"${p.name})" in generated
                           or f"${p.name} " in generated)
        ctx_hash = context_digest(context)
        checks = ("integrity", "provenance", "grain", "counts", "sums", "percentages", "duplicates", "cardinality", "partitions")
        material = {"sql": generated, "parameters": [asdict(p) for p in parameters],
                    "context": ctx_hash, "budget": asdict(visitor.budget), "grain": proposal.expected_grain,
                    "checks": checks, "relations": [asdict(r) for r in visitor.relations]}
        query_id = digest(material)
        result = ValidatedExploratoryQuery(
            canonical(tree), generated, tuple(sorted(visitor.sources)), tuple(sorted(visitor.columns)),
            tuple(sorted(visitor.functions)), tuple(visitor.relations), parameters, visitor.budget,
            tuple(sorted({t.permission for t in context.catalog.tables if t.name in visitor.sources})),
            query_id, ctx_hash, proposal.expected_grain, checks,
        )
        return SecurityDecision(Decision.ALLOW, "structurally_valid_synthetic_only" if context.catalog.synthetic_only
                                else "structurally_valid_supervised_foundation", query_id), result
    except Rejected as exc:
        return SecurityDecision(exc.decision, exc.reason), None
    except Exception:
        # Do not disclose engine diagnostics, paths, SQL, catalog or tenant names.
        return SecurityDecision(Decision.INVALID_QUERY, "invalid_query"), None
