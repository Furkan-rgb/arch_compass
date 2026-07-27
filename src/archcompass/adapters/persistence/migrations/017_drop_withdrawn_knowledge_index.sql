-- Remove the withdrawn embedding index over the method primer and the policy corpus.
--
-- It was built, measured and rejected: over 252 chunks it retrieved the right passage 7
-- times in 10 with a real embedding model and 2 in 10 with the deterministic one, and it
-- missed the primer's own "what the detector cannot see" section when asked exactly that.
-- The corpus is about 45,000 characters against an input budget near 490,000, so it is now
-- presented whole and nothing queries these tables.
--
-- Dropped rather than left in place. They are a derived cache holding no record anything
-- can regenerate from, and a table nothing reads is an invitation to wonder what it was for.
--
-- `IF EXISTS` throughout: a workspace created after the index was withdrawn never had them,
-- and one created during the window did. Both must reach the same schema.
--
-- The per-version vector tables this index created are named `knowledge_vectors_d<dim>_<id>`
-- and cannot be enumerated in static SQL. None was ever written — building one required an
-- embedding pass that no release performed — so there is nothing here to chase.

DROP TABLE IF EXISTS knowledge_vector_rows;
DROP TABLE IF EXISTS knowledge_chunks;
DROP TABLE IF EXISTS knowledge_index_versions;
