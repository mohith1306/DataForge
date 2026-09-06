-- DataForge Enterprise Tables Migration
-- Phase 1: Organizations, Projects, Users, API Keys, Reliability Graph

-- Organizations
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    environment VARCHAR(50) DEFAULT 'production',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, slug)
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(200),
    org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
    role VARCHAR(50) DEFAULT 'member',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    scopes JSONB DEFAULT '["read", "write"]',
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_user ON api_keys(user_id);

-- Reliability Graph Nodes
CREATE TABLE IF NOT EXISTS reliability_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    node_type VARCHAR(50) NOT NULL,
    name VARCHAR(500) NOT NULL,
    external_id VARCHAR(500),
    metadata JSONB DEFAULT '{}',
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    business_criticality VARCHAR(20) DEFAULT 'medium',
    reliability_score FLOAT DEFAULT 100.0,
    last_incident_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reliability_nodes_org ON reliability_nodes(org_id);
CREATE INDEX idx_reliability_nodes_type ON reliability_nodes(node_type);
CREATE INDEX idx_reliability_nodes_project ON reliability_nodes(project_id);
CREATE INDEX idx_reliability_nodes_external ON reliability_nodes(external_id);

-- Reliability Graph Edges
CREATE TABLE IF NOT EXISTS reliability_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES reliability_nodes(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES reliability_nodes(id) ON DELETE CASCADE,
    edge_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, edge_type)
);

CREATE INDEX idx_reliability_edges_source ON reliability_edges(source_id);
CREATE INDEX idx_reliability_edges_target ON reliability_edges(target_id);

-- Extend incidents table with enterprise columns
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS reliability_graph_snapshot JSONB;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS failure_dna VARCHAR(500);
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS business_impact_score FLOAT;

CREATE INDEX idx_incidents_org ON incidents(org_id);
CREATE INDEX idx_incidents_project ON incidents(project_id);
CREATE INDEX idx_incidents_failure_dna ON incidents(failure_dna);
