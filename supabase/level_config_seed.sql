-- ═══════════════════════════════════════════════════════════════════════════
-- Étape 1 — Table level_config (Besoin 2 : niveaux prérequis)
-- À exécuter dans le SQL Editor de Supabase.
-- Remplace toute liste de tables en dur dans le code Python.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS level_config (
    table_id    integer PRIMARY KEY,
    table_name  text    NOT NULL,
    level       integer NOT NULL,   -- 0 à 4
    sub_level   text,               -- NULL sauf niveau 3 (Ventes/Achats/Stock/Ressources/Immobilisations)
    note        text
);

-- N0 — Plan Comptable (prérequis absolu)
INSERT INTO level_config (table_id, table_name, level, sub_level, note) VALUES
(15, 'G/L Account', 0, NULL, 'Obligatoire — prérequis absolu avant tout autre niveau')
ON CONFLICT (table_id) DO NOTHING;

-- N1 — Operational Setup
INSERT INTO level_config (table_id, table_name, level, sub_level, note) VALUES
(3,   'Payment Terms',        1, NULL, 'Confirmé T2 — reconnu dans le package'),
(10,  'Shipment Method',      1, NULL, NULL),
(13,  'Salesperson/Purchaser',1, NULL, NULL),
(14,  'Location',             1, NULL, NULL),
(204, 'Unit of Measure',      1, NULL, NULL),
(289, 'Payment Method',       1, NULL, NULL)
ON CONFLICT (table_id) DO NOTHING;

-- N2 — Reference Data
INSERT INTO level_config (table_id, table_name, level, sub_level, note) VALUES
(4,    'Currency',       2, NULL, 'Confirmé Cas 3 — erreur si absent'),
(9,    'Country/Region', 2, NULL, 'Confirmé Cas 3 — erreur si absent'),
(5722, 'Item Category',  2, NULL, NULL)
ON CONFLICT (table_id) DO NOTHING;

-- N3 — Master Data (sous-niveaux indépendants entre eux)
INSERT INTO level_config (table_id, table_name, level, sub_level, note) VALUES
(18,   'Customer',              3, 'Ventes', 'Confirmé Cas 2, 3, 4'),
(5050, 'Contact',                3, 'Ventes', NULL),
(222,  'Ship-to Address',        3, 'Ventes', NULL),
(287,  'Customer Bank Account',  3, 'Ventes', NULL),

(23,   'Vendor',                 3, 'Achats', NULL),
(288,  'Vendor Bank Account',    3, 'Achats', NULL),
(26,   'Vendor Ledger Entry',    3, 'Achats', NULL),

(27,   'Item',                   3, 'Stock', 'Confirmé Cas 1'),
(5741, 'Item Variant',           3, 'Stock', NULL),
(5717, 'Item Reference',         3, 'Stock', NULL),
(5404, 'Item Unit of Measure',   3, 'Stock', NULL),

(156, 'Resource',       3, 'Ressources', NULL),
(76,  'Resource Group', 3, 'Ressources', NULL),

(5600, 'Fixed Asset',           3, 'Immobilisations', NULL),
(5601, 'FA Depreciation Book',  3, 'Immobilisations', NULL),
(5602, 'FA Allocation',         3, 'Immobilisations', NULL)
ON CONFLICT (table_id) DO NOTHING;

-- N4 — Transactional Data
INSERT INTO level_config (table_id, table_name, level, sub_level, note) VALUES
(81, 'Gen. Journal Line', 4, NULL, 'Soldes GL'),
(83, 'Item Journal Line', 4, NULL, 'Stocks'),
(36, 'Sales Header',      4, NULL, 'Documents vente ouverts'),
(37, 'Sales Line',        4, NULL, 'Documents vente ouverts'),
(38, 'Purchase Header',   4, NULL, 'Documents achat ouverts'),
(39, 'Purchase Line',     4, NULL, 'Documents achat ouverts')
ON CONFLICT (table_id) DO NOTHING;

-- Vérification rapide après exécution :
-- SELECT level, sub_level, count(*) FROM level_config GROUP BY level, sub_level ORDER BY level, sub_level;
