-- Addendum: structured evidence, never executable classification SQL.
CREATE TABLE IF NOT EXISTS business_concept_entity_links (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 concept_id uuid NOT NULL,
 version integer NOT NULL,
 entity_type text NOT NULL,
 source_namespace text NOT NULL,
 entity_key text,
 entity_label text NOT NULL,
 relationship text NOT NULL,
 validation_status text NOT NULL CHECK(validation_status IN ('proposed','source_verified')),
 valid_from date,
 valid_to date,
 evidence jsonb NOT NULL,
 actor_id uuid NOT NULL REFERENCES core_users(id),
 created_at_utc timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(concept_id,version) REFERENCES business_concept_versions(concept_id,version),
 UNIQUE NULLS NOT DISTINCT(concept_id,version,entity_type,source_namespace,entity_key,entity_label,relationship),
 CHECK(valid_to IS NULL OR (valid_from IS NOT NULL AND valid_to>valid_from))
);
CREATE TABLE IF NOT EXISTS business_concept_classification_rules (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 concept_id uuid NOT NULL,
 version integer NOT NULL,
 rule_code text NOT NULL,
 description text NOT NULL,
 input_fields jsonb NOT NULL,
 source text NOT NULL,
 validation_status text NOT NULL DEFAULT 'proposed' CHECK(validation_status IN ('proposed','historical_evidence')),
 valid_from date,
 valid_to date,
 limitations jsonb NOT NULL,
 actor_id uuid NOT NULL REFERENCES core_users(id),
 created_at_utc timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(concept_id,version) REFERENCES business_concept_versions(concept_id,version),
 UNIQUE(concept_id,version,rule_code),
 CHECK(valid_to IS NULL OR (valid_from IS NOT NULL AND valid_to>valid_from))
);
CREATE INDEX IF NOT EXISTS business_entity_concept_idx ON business_concept_entity_links(concept_id,version);
CREATE INDEX IF NOT EXISTS business_rules_concept_idx ON business_concept_classification_rules(concept_id,version);
-- Evidence is append-only. Corrections get a new concept version, not retrospective edits.
DROP TRIGGER IF EXISTS business_entity_immutable ON business_concept_entity_links;
CREATE TRIGGER business_entity_immutable BEFORE UPDATE OR DELETE ON business_concept_entity_links
 FOR EACH ROW EXECUTE FUNCTION business_semantics_immutable_guard();
DROP TRIGGER IF EXISTS business_rule_immutable ON business_concept_classification_rules;
CREATE TRIGGER business_rule_immutable BEFORE UPDATE OR DELETE ON business_concept_classification_rules
 FOR EACH ROW EXECUTE FUNCTION business_semantics_immutable_guard();
