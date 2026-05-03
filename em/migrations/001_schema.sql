-- ============================================================
--  Estate Mind — Schéma PostgreSQL Complet
--  Base cible : estate_mind
--  Commande   : psql -U postgres -d estate_mind -f migrations/001_schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Table principale : annonces immobilières ─────────────────
CREATE TABLE IF NOT EXISTS estate_mind_db (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    source           VARCHAR(64) NOT NULL DEFAULT 'manual',
    listing_id       VARCHAR(128) NOT NULL,
    transaction_type VARCHAR(32),
    property_type    VARCHAR(64),
    title            VARCHAR(512),
    description      TEXT,
    price_value      DOUBLE PRECISION,
    currency         VARCHAR(8)  DEFAULT 'TND',
    surface_m2       DOUBLE PRECISION,
    bedrooms         DOUBLE PRECISION,
    bathrooms        DOUBLE PRECISION,
    city             VARCHAR(128),
    district         VARCHAR(128),
    region           VARCHAR(128),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    url              VARCHAR(512),
    scraped_at       TIMESTAMPTZ,
    extras           JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_estate_mind_db UNIQUE (source, listing_id)
);

CREATE INDEX IF NOT EXISTS ix_em_city     ON estate_mind_db (city);
CREATE INDEX IF NOT EXISTS ix_em_tx       ON estate_mind_db (transaction_type);
CREATE INDEX IF NOT EXISTS ix_em_price    ON estate_mind_db (price_value);
CREATE INDEX IF NOT EXISTS ix_em_type     ON estate_mind_db (property_type);
CREATE INDEX IF NOT EXISTS ix_em_bedrooms ON estate_mind_db (bedrooms);
CREATE INDEX IF NOT EXISTS ix_em_surface  ON estate_mind_db (surface_m2);

-- ── Utilisateurs ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    email      VARCHAR(256) UNIQUE NOT NULL,
    username   VARCHAR(128),
    lang_pref  VARCHAR(8)  DEFAULT 'fr',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Sessions de chat ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Interactions (historique complet) ────────────────────────
CREATE TABLE IF NOT EXISTS chat_interactions (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sequence_number     INTEGER     NOT NULL DEFAULT 1,
    original_query      TEXT        NOT NULL,
    detected_language   VARCHAR(10) NOT NULL DEFAULT 'unknown',
    translated_query    TEXT,
    detected_intent     VARCHAR(64),
    intent_confidence   DOUBLE PRECISION,
    intent_probabilities JSONB,
    routed_to_agent     VARCHAR(64),
    agent_url           VARCHAR(256),
    agent_raw_response  JSONB,
    response_text       TEXT,
    explanation_json    JSONB,
    pipeline_steps_json JSONB,
    confidence_score    DOUBLE PRECISION CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
    report_generated    BOOLEAN     NOT NULL DEFAULT FALSE,
    report_path         VARCHAR(512),
    processing_ms       INTEGER,
    error_message       TEXT,
    is_darija           BOOLEAN     DEFAULT FALSE,
    darija_terms        JSONB,
    top_ngrams          JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_inter_session  ON chat_interactions (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_inter_intent   ON chat_interactions (detected_intent);
CREATE INDEX IF NOT EXISTS ix_inter_date     ON chat_interactions (created_at DESC);

-- ── Rapports PDF ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS report_records (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    report_type     VARCHAR(64) NOT NULL,
    file_path       VARCHAR(512) NOT NULL,
    file_size_bytes INTEGER,
    parameters      JSONB,
    summary         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_reports_session ON report_records (session_id, created_at DESC);

-- ── Historique des prix (analytics) ─────────────────────────
CREATE TABLE IF NOT EXISTS price_history (
    id               UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    city             VARCHAR(128) NOT NULL,
    property_type    VARCHAR(64),
    transaction_type VARCHAR(32),
    avg_price        DOUBLE PRECISION,
    median_price     DOUBLE PRECISION,
    total_listings   INTEGER,
    period_month     VARCHAR(7),
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Logs NLP (pour évaluation) ───────────────────────────────
CREATE TABLE IF NOT EXISTS nlp_evaluation_logs (
    id                UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    interaction_id    UUID        REFERENCES chat_interactions(id) ON DELETE CASCADE,
    raw_input         TEXT,
    detected_lang     VARCHAR(10),
    is_tunisian       BOOLEAN     DEFAULT FALSE,
    normalized_text   TEXT,
    translated_text   TEXT,
    intent            VARCHAR(64),
    intent_confidence DOUBLE PRECISION,
    true_intent       VARCHAR(64),
    is_correct        BOOLEAN,
    top_ngrams        JSONB,
    vocab_size        INTEGER,
    processing_ms     INTEGER,
    model_version     VARCHAR(32) DEFAULT 'naive_bayes_v1',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Trigger : updated_at auto ────────────────────────────────
CREATE OR REPLACE FUNCTION fn_update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_sessions_upd ON chat_sessions;
CREATE TRIGGER trg_sessions_upd
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- ── Vue analytique principale ────────────────────────────────
CREATE OR REPLACE VIEW v_market_by_city AS
SELECT
    city,
    COUNT(*)                                                              AS total_listings,
    COUNT(*) FILTER (WHERE transaction_type = 'vente')                   AS for_sale,
    COUNT(*) FILTER (WHERE transaction_type = 'location')                AS for_rent,
    ROUND(AVG(price_value) FILTER (WHERE transaction_type='vente'   AND price_value>0)::numeric,0) AS avg_sale_price,
    ROUND(AVG(price_value) FILTER (WHERE transaction_type='location' AND price_value>0)::numeric,0) AS avg_rent_price,
    ROUND(AVG(price_value/NULLIF(surface_m2,0)) FILTER (WHERE price_value>0 AND surface_m2>0)::numeric,0) AS avg_price_per_m2,
    ROUND(AVG(surface_m2) FILTER (WHERE surface_m2>0)::numeric,1)        AS avg_surface
FROM estate_mind_db
WHERE city IS NOT NULL AND city <> 'unknown'
GROUP BY city ORDER BY total_listings DESC;

-- ── Vue rendement investissement ────────────────────────────
CREATE OR REPLACE VIEW v_investment_yields AS
WITH
  sale AS (
    SELECT city, district, AVG(price_value) AS avg_sale, COUNT(*) AS n_sale
    FROM estate_mind_db WHERE transaction_type='vente' AND price_value>0
    GROUP BY city, district HAVING COUNT(*) >= 2
  ),
  rent AS (
    SELECT city, district, AVG(price_value) AS avg_rent, COUNT(*) AS n_rent
    FROM estate_mind_db WHERE transaction_type='location' AND price_value>0
    GROUP BY city, district HAVING COUNT(*) >= 2
  )
SELECT s.city, s.district,
    ROUND(s.avg_sale::numeric,0)                                              AS avg_sale_price,
    ROUND(r.avg_rent::numeric,0)                                              AS avg_monthly_rent,
    ROUND((r.avg_rent*12/NULLIF(s.avg_sale,0)*100)::numeric,2)               AS gross_yield_pct,
    s.n_sale, r.n_rent
FROM sale s JOIN rent r ON s.city=r.city AND s.district=r.district
ORDER BY gross_yield_pct DESC;

-- ── Données de test réalistes ────────────────────────────────
INSERT INTO estate_mind_db (source,listing_id,transaction_type,property_type,title,price_value,surface_m2,bedrooms,bathrooms,city,district,region,latitude,longitude,scraped_at) VALUES
('tayara','T001','vente','appartement','Appartement S+2 Menzah 6',285000,85,2,1,'Tunis','Menzah 6','Grand Tunis',36.850,10.200,'2025-01-15'),
('tayara','T002','vente','appartement','S+3 La Marsa vue mer',520000,120,3,2,'Tunis','La Marsa','Grand Tunis',36.878,10.325,'2025-01-16'),
('tayara','T003','vente','villa','Villa S+4 Carthage jardin',950000,280,4,3,'Tunis','Carthage','Grand Tunis',36.857,10.324,'2025-01-17'),
('tayara','T004','vente','appartement','S+1 centre ville Tunis',155000,55,1,1,'Tunis','Centre','Grand Tunis',36.819,10.165,'2025-01-18'),
('tayara','T005','vente','terrain','Terrain résidentiel El Aouina',320000,400,0,0,'Tunis','El Aouina','Grand Tunis',36.844,10.227,'2025-01-19'),
('mubawab','T006','vente','appartement','S+2 neuf Ain Zaghouan',195000,90,2,1,'Tunis','Ain Zaghouan','Grand Tunis',36.882,10.204,'2025-01-20'),
('tayara','T007','vente','appartement','S+3 Jardins de Carthage',380000,110,3,2,'Tunis','Jardins Carthage','Grand Tunis',36.849,10.310,'2025-01-21'),
('tayara','T008','vente','villa','Villa moderne Gammarth',1200000,350,5,4,'Tunis','Gammarth','Grand Tunis',36.920,10.290,'2025-01-22'),
('tayara','T009','location','appartement','S+2 meublé Lac 2',1800,80,2,1,'Tunis','Lac 2','Grand Tunis',36.837,10.235,'2025-01-23'),
('tayara','T010','location','studio','Studio El Manar',850,45,1,1,'Tunis','El Manar','Grand Tunis',36.841,10.191,'2025-01-24'),
('mubawab','T011','location','appartement','S+3 Menzah 9',2200,115,3,2,'Tunis','Menzah 9','Grand Tunis',36.859,10.198,'2025-01-25'),
('tayara','T012','vente','appartement','S+2 El Ghazela résidence',210000,88,2,1,'Tunis','El Ghazela','Grand Tunis',36.880,10.196,'2025-01-26'),
('tayara','T013','vente','appartement','Duplex S+4 Mutuelleville',680000,165,4,2,'Tunis','Mutuelleville','Grand Tunis',36.834,10.182,'2025-01-27'),
('tayara','T014','location','appartement','S+1 Belvédère meublé',750,52,1,1,'Tunis','Belvédère','Grand Tunis',36.826,10.175,'2025-01-28'),
('tayara','A001','vente','appartement','S+2 Ariana Soghra',175000,78,2,1,'Ariana','Ariana Soghra','Grand Tunis',36.862,10.161,'2025-01-29'),
('tayara','A002','vente','appartement','S+3 Riadh Andalous',235000,105,3,2,'Ariana','Riadh Andalous','Grand Tunis',36.875,10.190,'2025-01-30'),
('tayara','A003','vente','villa','Villa S+4 Borj Louzir',580000,220,4,3,'Ariana','Borj Louzir','Grand Tunis',36.900,10.200,'2025-02-01'),
('mubawab','A004','location','appartement','S+2 Ariana centre',1200,75,2,1,'Ariana','Centre','Grand Tunis',36.862,10.161,'2025-02-02'),
('tayara','A005','vente','appartement','S+2 Mnihla neuf promoteur',145000,72,2,1,'Ariana','Mnihla','Grand Tunis',36.890,10.170,'2025-02-03'),
('tayara','A006','location','appartement','S+1 Raoued',700,48,1,1,'Ariana','Raoued','Grand Tunis',36.900,10.145,'2025-02-04'),
('tayara','A007','vente','appartement','S+3 Ettahrir',265000,98,3,2,'Ariana','Ettahrir','Grand Tunis',36.868,10.180,'2025-02-05'),
('tayara','S001','vente','appartement','S+2 Sousse centre',165000,80,2,1,'Sousse','Centre','Sahel',35.825,10.636,'2025-02-06'),
('tayara','S002','vente','appartement','S+3 Khezama Est',220000,100,3,2,'Sousse','Khezama','Sahel',35.840,10.650,'2025-02-07'),
('tayara','S003','vente','villa','Villa bord mer Hammam Sousse',750000,300,5,3,'Sousse','Hammam Sousse','Sahel',35.860,10.590,'2025-02-08'),
('mubawab','S004','location','appartement','S+2 Sahloul meublé',1100,82,2,1,'Sousse','Sahloul','Sahel',35.830,10.620,'2025-02-09'),
('tayara','S005','vente','terrain','Terrain zone touristique',280000,500,0,0,'Sousse','Hammam Sousse','Sahel',35.860,10.590,'2025-02-10'),
('tayara','S006','location','appartement','S+1 Sousse médina',650,48,1,1,'Sousse','Médina','Sahel',35.825,10.636,'2025-02-11'),
('tayara','S007','vente','appartement','S+2 Akouda',150000,76,2,1,'Sousse','Akouda','Sahel',35.875,10.572,'2025-02-12'),
('tayara','SF001','vente','appartement','S+2 Sfax centre',120000,75,2,1,'Sfax','Centre','Centre-Est',34.739,10.760,'2025-02-13'),
('tayara','SF002','vente','villa','Villa route Gremda',320000,200,4,2,'Sfax','Gremda','Centre-Est',34.760,10.780,'2025-02-14'),
('mubawab','SF003','location','appartement','S+2 Sfax meublé',800,70,2,1,'Sfax','Centre','Centre-Est',34.739,10.760,'2025-02-15'),
('tayara','SF004','vente','appartement','S+3 Sakiet Ezzit',155000,95,3,2,'Sfax','Sakiet Ezzit','Centre-Est',34.780,10.740,'2025-02-16'),
('tayara','N001','vente','villa','Villa Hammamet nord vue mer',680000,250,4,3,'Nabeul','Hammamet Nord','Cap Bon',36.400,10.500,'2025-02-17'),
('tayara','N002','vente','appartement','S+2 Nabeul plage',185000,82,2,1,'Nabeul','Centre','Cap Bon',36.456,10.735,'2025-02-18'),
('mubawab','N003','location','villa','Villa meublée Hammamet été',3500,180,3,2,'Nabeul','Hammamet','Cap Bon',36.400,10.500,'2025-02-19'),
('tayara','BN001','vente','appartement','S+2 Ezzahra',165000,78,2,1,'Ben Arous','Ezzahra','Grand Tunis',36.750,10.230,'2025-02-20'),
('tayara','BN002','vente','appartement','S+3 Mégrine',195000,100,3,2,'Ben Arous','Mégrine','Grand Tunis',36.770,10.210,'2025-02-21'),
('tayara','BN003','location','appartement','S+2 Radès meublé',1000,75,2,1,'Ben Arous','Radès','Grand Tunis',36.764,10.275,'2025-02-22'),
('tayara','M001','vente','appartement','S+2 Monastir ville',145000,72,2,1,'Monastir','Centre','Sahel',35.764,10.811,'2025-02-23'),
('tayara','M002','vente','villa','Villa Skanes bord mer',520000,220,4,3,'Monastir','Skanes','Sahel',35.750,10.780,'2025-02-24'),
('tayara','BIZ001','vente','appartement','S+2 Bizerte corniche',140000,70,2,1,'Bizerte','Corniche','Nord',37.274,9.873,'2025-02-25'),
('tayara','BIZ002','location','appartement','S+1 Bizerte centre',600,45,1,1,'Bizerte','Centre','Nord',37.274,9.873,'2025-02-26'),
('tayara','GAB001','vente','appartement','S+2 Gabès centre',95000,70,2,1,'Gabès','Centre','Sud-Est',33.881,10.097,'2025-02-27'),
('tayara','KAI001','vente','appartement','S+2 Kairouan',85000,68,2,1,'Kairouan','Centre','Centre-Ouest',35.678,10.096,'2025-02-28')
ON CONFLICT (source, listing_id) DO NOTHING;

INSERT INTO users (id,email,username,lang_pref) VALUES
('11111111-1111-1111-1111-111111111111','ahmed@test.tn','ahmed_ben_ali','fr'),
('22222222-2222-2222-2222-222222222222','fatima@test.tn','fatima_gharbi','ar'),
('33333333-3333-3333-3333-333333333333','john@test.com','john_doe','en')
ON CONFLICT (email) DO NOTHING;

INSERT INTO price_history (city,property_type,transaction_type,avg_price,median_price,total_listings,period_month) VALUES
('Tunis','appartement','vente',320000,285000,142,'2025-01'),
('Tunis','appartement','location',1450,1300,98,'2025-01'),
('Tunis','villa','vente',950000,850000,28,'2025-01'),
('Ariana','appartement','vente',210000,195000,87,'2025-01'),
('Ariana','appartement','location',1150,1100,62,'2025-01'),
('Sousse','appartement','vente',190000,170000,74,'2025-01'),
('Sousse','appartement','location',1000,950,45,'2025-01'),
('Sfax','appartement','vente',135000,120000,68,'2025-01'),
('Nabeul','appartement','vente',180000,165000,52,'2025-01'),
('Ben Arous','appartement','vente',175000,165000,41,'2025-01'),
('Monastir','appartement','vente',152000,145000,35,'2025-01'),
('Bizerte','appartement','vente',138000,130000,29,'2025-01');

SELECT 'Schema OK' AS status,
       (SELECT COUNT(*) FROM estate_mind_db) AS listings,
       (SELECT COUNT(*) FROM users) AS users_count;
