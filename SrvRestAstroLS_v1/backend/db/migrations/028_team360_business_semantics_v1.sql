-- DEV controlled migration. Existing Console identities/organizations are authoritative.
-- Extension is already installed in inspected DEV; fail rather than simulate vectors.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS business_concepts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id uuid NOT NULL REFERENCES core_organizations(id),
 workspace_id uuid REFERENCES core_workspaces(id),
 module_code text,
 semantic_code text NOT NULL,
 status text NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','published','retired')),
 current_version integer,
 created_at_utc timestamptz NOT NULL DEFAULT now(),
 updated_at_utc timestamptz NOT NULL DEFAULT now(),
 UNIQUE NULLS NOT DISTINCT (organization_id,workspace_id,module_code,semantic_code)
);
CREATE TABLE IF NOT EXISTS business_concept_versions (
 concept_id uuid NOT NULL REFERENCES business_concepts(id),
 version integer NOT NULL CHECK(version>0),
 previous_version integer,
 canonical_name text NOT NULL,
 definition text NOT NULL,
 concept_type text NOT NULL,
 operational_context jsonb NOT NULL DEFAULT '{}',
 source text NOT NULL,
 reason text NOT NULL,
 actor_id uuid NOT NULL REFERENCES core_users(id),
 approved_by uuid REFERENCES core_users(id),
 approval_status text NOT NULL DEFAULT 'proposed' CHECK(approval_status IN ('proposed','published')),
 created_at_utc timestamptz NOT NULL DEFAULT now(),
 published_at_utc timestamptz,
 PRIMARY KEY(concept_id,version),
 FOREIGN KEY(concept_id,previous_version) REFERENCES business_concept_versions(concept_id,version),
 CHECK((approval_status='published')=(approved_by IS NOT NULL AND published_at_utc IS NOT NULL))
);
ALTER TABLE business_concepts DROP CONSTRAINT IF EXISTS business_concepts_current_version_fkey;
ALTER TABLE business_concepts ADD CONSTRAINT business_concepts_current_version_fkey
 FOREIGN KEY(id,current_version) REFERENCES business_concept_versions(concept_id,version);
CREATE TABLE IF NOT EXISTS business_concept_aliases (
 concept_id uuid NOT NULL,
 version integer NOT NULL,
 original_text text NOT NULL,
 normalized_text text NOT NULL,
 PRIMARY KEY(concept_id,version,normalized_text),
 FOREIGN KEY(concept_id,version) REFERENCES business_concept_versions(concept_id,version)
);
CREATE TABLE IF NOT EXISTS business_concept_embeddings (
 concept_id uuid NOT NULL,
 version integer NOT NULL,
 model_alias text NOT NULL,
 model_revision text NOT NULL,
 dimension integer NOT NULL CHECK(dimension>0),
 content_hash text NOT NULL,
 embedding vector NOT NULL,
 generated_at_utc timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(concept_id,version,model_alias,model_revision,dimension),
 FOREIGN KEY(concept_id,version) REFERENCES business_concept_versions(concept_id,version),
 CHECK(vector_dims(embedding)=dimension)
);
CREATE TABLE IF NOT EXISTS business_concept_capability_links (
 concept_id uuid NOT NULL,
 version integer NOT NULL,
 capability_code text NOT NULL,
 maturity text NOT NULL CHECK(maturity IN ('proposed','validated')),
 PRIMARY KEY(concept_id,version,capability_code),
 FOREIGN KEY(concept_id,version) REFERENCES business_concept_versions(concept_id,version)
);
CREATE TABLE IF NOT EXISTS business_concept_observations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 organization_id uuid NOT NULL REFERENCES core_organizations(id),
 workspace_id uuid NOT NULL REFERENCES core_workspaces(id),
 module_code text NOT NULL,
 expression_hash text NOT NULL,
 -- No raw chat, user identifier or free-form sensitive context retained.
 review_status text NOT NULL DEFAULT 'pending',
 occurrences integer NOT NULL DEFAULT 1,
 created_at_utc timestamptz NOT NULL DEFAULT now(),
 last_seen_at_utc timestamptz NOT NULL DEFAULT now(),
 UNIQUE(organization_id,workspace_id,module_code,expression_hash)
);
CREATE INDEX IF NOT EXISTS business_concepts_scope_idx ON business_concepts(organization_id,workspace_id,module_code,status);
CREATE INDEX IF NOT EXISTS business_alias_normalized_idx ON business_concept_aliases(normalized_text);
CREATE INDEX IF NOT EXISTS business_definition_fts_idx ON business_concept_versions USING gin
 (to_tsvector('spanish',canonical_name || ' ' || definition));
CREATE OR REPLACE FUNCTION business_semantics_scope_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.workspace_id IS NOT NULL AND NOT EXISTS(
  SELECT 1 FROM core_workspaces WHERE id=NEW.workspace_id AND organization_id=NEW.organization_id
 ) THEN RAISE EXCEPTION 'business_semantics_workspace_organization_mismatch'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS business_concepts_scope_guard ON business_concepts;
CREATE TRIGGER business_concepts_scope_guard BEFORE INSERT OR UPDATE ON business_concepts
 FOR EACH ROW EXECUTE FUNCTION business_semantics_scope_guard();
DROP TRIGGER IF EXISTS business_observations_scope_guard ON business_concept_observations;
CREATE TRIGGER business_observations_scope_guard BEFORE INSERT OR UPDATE ON business_concept_observations
 FOR EACH ROW EXECUTE FUNCTION business_semantics_scope_guard();
CREATE OR REPLACE FUNCTION business_semantics_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'business_semantics_history_immutable'; END IF;
 IF TG_TABLE_NAME='business_concept_versions' AND OLD.approval_status='proposed' AND
  (to_jsonb(OLD)-ARRAY['approval_status','approved_by','published_at_utc']) =
  (to_jsonb(NEW)-ARRAY['approval_status','approved_by','published_at_utc']) THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'business_semantics_published_definition_immutable';
END $$;
DROP TRIGGER IF EXISTS business_versions_immutable ON business_concept_versions;
CREATE TRIGGER business_versions_immutable BEFORE UPDATE OR DELETE ON business_concept_versions
 FOR EACH ROW EXECUTE FUNCTION business_semantics_immutable_guard();
CREATE OR REPLACE FUNCTION business_semantics_alias_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM business_concept_versions WHERE concept_id=COALESCE(NEW.concept_id,OLD.concept_id)
 AND version=COALESCE(NEW.version,OLD.version) AND approval_status='published') THEN
 RAISE EXCEPTION 'business_semantics_published_alias_immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS business_alias_immutable ON business_concept_aliases;
CREATE TRIGGER business_alias_immutable BEFORE INSERT OR UPDATE OR DELETE ON business_concept_aliases
 FOR EACH ROW EXECUTE FUNCTION business_semantics_alias_guard();
