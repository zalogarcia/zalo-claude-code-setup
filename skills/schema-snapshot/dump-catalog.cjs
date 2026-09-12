const { Client } = require('/Users/zalo/dev/delta-agents/node_modules/pg');
const fs = require('fs');
const out = process.argv[2];
const Q1 = `SELECT c.table_name, string_agg(c.column_name || '|' || (CASE WHEN c.data_type IN ('USER-DEFINED','ARRAY') THEN c.udt_name ELSE c.data_type END) || (CASE WHEN c.character_maximum_length IS NOT NULL THEN '(' || c.character_maximum_length || ')' ELSE '' END) || '|' || c.is_nullable || '|' || COALESCE(c.column_default, ''), E'\n' ORDER BY c.ordinal_position) AS cols
FROM information_schema.columns c JOIN pg_class pc ON pc.relname = c.table_name JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = 'public'
WHERE c.table_schema = 'public' AND pc.relkind = 'r' GROUP BY c.table_name ORDER BY c.table_name`;
const Q2 = `SELECT conrelid::regclass::text AS table_name, pg_get_constraintdef(oid) AS fk_def FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace AND conparentid = 0 ORDER BY conrelid::regclass::text, conname`;
const Q3 = `SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname`;
const Q4 = `SELECT c.relname AS table_name, c.relkind, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced, string_agg(a.attname || '|' || format_type(a.atttypid, a.atttypmod) || '|' || (CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END) || '|' || COALESCE(pg_get_expr(d.adbin, d.adrelid), ''), E'\n' ORDER BY a.attnum) AS cols
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE n.nspname = 'public' AND c.relkind = 'p' GROUP BY c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity ORDER BY c.relname`;
const Q5 = `SELECT c.relname AS view_name, string_agg(a.attname || '|' || format_type(a.atttypid, a.atttypmod), E'\n' ORDER BY a.attnum) AS cols, pg_get_viewdef(c.oid, true) AS def, (SELECT coalesce(bool_or(o LIKE 'security_invoker=%true%'), false) FROM unnest(c.reloptions) o) AS security_invoker
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = 'public' AND c.relkind = 'v' GROUP BY c.relname, c.oid, c.reloptions ORDER BY c.relname`;
(async () => {
  const c = new Client({ connectionString: process.env.SUPABASE_SESSION_POOLER_URL, ssl: { rejectUnauthorized: false }, statement_timeout: 60000 });
  await c.connect();
  const [r1, r2, r3, r4, r5] = await Promise.all([c.query(Q1), c.query(Q2), c.query(Q3), c.query(Q4), c.query(Q5)]);
  fs.writeFileSync(out + '/columns_raw.json', JSON.stringify(r1.rows));
  fs.writeFileSync(out + '/fks.json', JSON.stringify(r2.rows));
  fs.writeFileSync(out + '/rls_raw.json', JSON.stringify(r3.rows));
  fs.writeFileSync(out + '/parents.json', JSON.stringify(r4.rows));
  fs.writeFileSync(out + '/views.json', JSON.stringify(r5.rows));
  console.log('leaf tables', r1.rows.length, '| fks', r2.rows.length, '| rls rows', r3.rows.length, '| parents', r4.rows.length, '| views', r5.rows.length);
  await c.end();
})().catch(e => { console.error('DUMP_FAILED', e.message); process.exit(1); });
