--
-- PostgreSQL database dump
--

\restrict OrMckDDdjbetmJSJnanA1lknCcCEwTR5w1JeMkMMUcsCrwrfae3eSLeU8zijLck

-- Dumped from database version 18.4 (Debian 18.4-1.pgdg13+1)
-- Dumped by pg_dump version 18.4 (Debian 18.4-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: core_organization_member_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_organization_member_roles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_member_id uuid NOT NULL,
    role_code text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    updated_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_core_organization_member_roles_status CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text, 'archived'::text])))
);


--
-- Name: core_organization_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_organization_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    updated_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_core_organization_members_status CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text, 'archived'::text])))
);


--
-- Name: core_organization_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_organization_roles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    role_code text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    updated_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_core_organization_roles_status CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text, 'archived'::text])))
);


--
-- Name: core_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_code text NOT NULL,
    display_name text NOT NULL,
    primary_type text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    parent_organization_id uuid,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    updated_at_utc timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_core_organizations_primary_type CHECK ((primary_type = ANY (ARRAY['platform_owner'::text, 'partner'::text, 'client'::text, 'internal_client'::text, 'demo_client'::text]))),
    CONSTRAINT chk_core_organizations_status CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text, 'archived'::text])))
);


--
-- Name: core_organization_member_roles core_organization_member_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_member_roles
    ADD CONSTRAINT core_organization_member_roles_pkey PRIMARY KEY (id);


--
-- Name: core_organization_members core_organization_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_members
    ADD CONSTRAINT core_organization_members_pkey PRIMARY KEY (id);


--
-- Name: core_organization_roles core_organization_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_roles
    ADD CONSTRAINT core_organization_roles_pkey PRIMARY KEY (id);


--
-- Name: core_organizations core_organizations_organization_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organizations
    ADD CONSTRAINT core_organizations_organization_code_key UNIQUE (organization_code);


--
-- Name: core_organizations core_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organizations
    ADD CONSTRAINT core_organizations_pkey PRIMARY KEY (id);


--
-- Name: core_organization_member_roles uq_core_organization_member_roles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_member_roles
    ADD CONSTRAINT uq_core_organization_member_roles_code UNIQUE (organization_member_id, role_code);


--
-- Name: core_organization_members uq_core_organization_members_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_members
    ADD CONSTRAINT uq_core_organization_members_user UNIQUE (organization_id, user_id);


--
-- Name: core_organization_roles uq_core_organization_roles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_roles
    ADD CONSTRAINT uq_core_organization_roles_code UNIQUE (organization_id, role_code);


--
-- Name: idx_core_organization_member_roles_member; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organization_member_roles_member ON public.core_organization_member_roles USING btree (organization_member_id);


--
-- Name: idx_core_organization_members_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organization_members_org ON public.core_organization_members USING btree (organization_id);


--
-- Name: idx_core_organization_members_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organization_members_user ON public.core_organization_members USING btree (user_id);


--
-- Name: idx_core_organization_roles_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organization_roles_org ON public.core_organization_roles USING btree (organization_id);


--
-- Name: idx_core_organizations_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organizations_parent ON public.core_organizations USING btree (parent_organization_id);


--
-- Name: idx_core_organizations_primary_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_core_organizations_primary_type ON public.core_organizations USING btree (primary_type);


--
-- Name: core_organization_member_roles core_organization_member_roles_organization_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_member_roles
    ADD CONSTRAINT core_organization_member_roles_organization_member_id_fkey FOREIGN KEY (organization_member_id) REFERENCES public.core_organization_members(id) ON DELETE CASCADE;


--
-- Name: core_organization_members core_organization_members_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_members
    ADD CONSTRAINT core_organization_members_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.core_organizations(id) ON DELETE CASCADE;


--
-- Name: core_organization_members core_organization_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_members
    ADD CONSTRAINT core_organization_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.core_users(id) ON DELETE CASCADE;


--
-- Name: core_organization_roles core_organization_roles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organization_roles
    ADD CONSTRAINT core_organization_roles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.core_organizations(id) ON DELETE CASCADE;


--
-- Name: core_organizations core_organizations_parent_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_organizations
    ADD CONSTRAINT core_organizations_parent_organization_id_fkey FOREIGN KEY (parent_organization_id) REFERENCES public.core_organizations(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict OrMckDDdjbetmJSJnanA1lknCcCEwTR5w1JeMkMMUcsCrwrfae3eSLeU8zijLck

