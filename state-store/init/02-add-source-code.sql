-- Migration: add source_code column to tool_registry for dynamic tool loading.
-- Safe to re-run: uses IF NOT EXISTS.
ALTER TABLE tool_registry ADD COLUMN IF NOT EXISTS source_code TEXT;
