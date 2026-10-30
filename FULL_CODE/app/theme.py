"""Visual theme: white surfaces, deep navy brand colour, one blue accent. All styling lives here."""

NAVY = "#0B1F3A"
BLUE = "#1D4ED8"

HEAD_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --navy: #0B1F3A; --navy-2: #15305A; --blue: #1D4ED8; --blue-soft: #EAF0FD; --ink: #0F172A; --muted: #64748B;
  --line: #E3E8EF; --bg: #F4F6FA;
  --ok: #047857; --ok-bg: #E9F8F1; --warn: #B45309; --warn-bg: #FFF6E5; --bad: #B91C1C; --bad-bg: #FDEDED;
}
body { background: var(--bg); color: var(--ink);
       font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
.nicegui-content { padding: 0; }
.q-tab-panels, .q-tab-panel { background: transparent !important; padding: 0 !important; }

/* header */
.ss-header { background: var(--navy); box-shadow: 0 1px 0 rgba(255,255,255,.06); }
.ss-logo { width: 34px; height: 34px; border-radius: 9px; background: linear-gradient(135deg,#3B82F6,#1D4ED8);
           display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 17px; }
.ss-wordmark { font-weight: 700; font-size: 17px; letter-spacing: -.01em; color: #fff; }
.ss-tagline { font-size: 11.5px; color: #9FB3D1; }
.ss-tabs .q-tab { color: #B8C7DD; text-transform: none; font-weight: 600; letter-spacing: 0; }
.ss-tabs .q-tab--active { color: #fff; }

/* hero + search box */
.ss-hero { background: linear-gradient(180deg, var(--navy) 0%, var(--navy-2) 100%); padding: 34px 24px 64px; }
.ss-hero h1 { color: #fff; font-size: 30px; line-height: 1.2; font-weight: 700; letter-spacing: -.02em; margin: 0; }
.ss-hero p { color: #A9BCD8; margin: 6px 0 0; font-size: 14.5px; line-height: 1.4; }
.ss-searchbox { background: #fff; border-radius: 14px; padding: 6px 6px 6px 16px; width: 100%;
                box-shadow: 0 18px 40px rgba(3,12,28,.28); }
.ss-searchbox .q-field__control { height: 48px; }
.ss-searchbox input { font-size: 16.5px !important; color: var(--ink) !important; }
.ss-search-btn { background: var(--blue) !important; color: #fff !important; border-radius: 10px !important;
                 height: 46px; padding: 0 22px !important; font-weight: 600; text-transform: none; }
.ss-try-label { color: #8EA3C3; font-size: 12.5px; font-weight: 600; }
.ss-try { background: rgba(255,255,255,.08) !important; color: #DCE6F5 !important; border: 1px solid rgba(255,255,255,.14);
          border-radius: 999px !important; font-size: 12.5px !important; text-transform: none !important;
          padding: 2px 12px !important; min-height: 28px !important; }
.ss-try:hover { background: rgba(255,255,255,.16) !important; }
.ss-try .q-btn__content, .ss-try.text-primary { color: #DCE6F5 !important; }
.ss-legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 12px; color: #475569; }
.ss-legend span.dot { display: inline-block; width: 9px; height: 9px; border-radius: 3px; margin-right: 5px; }

/* page body */
.ss-body { max-width: 1240px; margin: -36px auto 0; padding: 0 24px 40px; width: 100%; }
.ss-panel { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; }
.ss-kicker { font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.ss-understood { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.ss-tag { background: var(--blue-soft); color: #1E3A8A; border-radius: 7px; padding: 3px 9px; font-size: 12.5px;
          font-weight: 500; }
.ss-tag.dim { background: #F1F5F9; color: #475569; }
.ss-count { font-size: 14px; color: var(--muted); }
.ss-count b { color: var(--ink); }
.ss-notice { display: flex; gap: 10px; align-items: flex-start; border-radius: 12px; padding: 11px 14px; font-size: 13.5px; }
.ss-notice.info { background: var(--blue-soft); color: #1E3A8A; }
.ss-notice.warn { background: var(--warn-bg); color: #7C3E06; }

/* product grid + cards */
.ss-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(214px, 1fr)); gap: 16px; width: 100%; }
.ss-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; cursor: pointer;
           transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
           display: flex; flex-direction: column; }
.ss-card:hover { transform: translateY(-3px); box-shadow: 0 14px 30px rgba(11,31,58,.12); border-color: #CBD5E1; }
.ss-card.dim { opacity: .78; }
.ss-thumb { height: 138px; position: relative; display: flex; align-items: center; justify-content: center;
            background: radial-gradient(circle at 30% 20%, #F3F7FF 0%, #E4ECFB 70%); }
.ss-thumb .q-icon { font-size: 54px; color: #2F55C8; opacity: .9; }
.ss-thumb-cap { position: absolute; left: 10px; bottom: 8px; font-size: 10px; color: #7A8CA8; letter-spacing: .05em;
                text-transform: uppercase; font-weight: 600; }
.ss-rank { position: absolute; top: 10px; left: 10px; background: var(--navy); color: #fff; font-size: 11px;
           font-weight: 700; border-radius: 6px; padding: 1px 7px; }
.ss-card-body { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
.ss-brand { font-size: 10.5px; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); font-weight: 700; }
.ss-title { font-size: 13.5px; font-weight: 600; line-height: 1.35; color: var(--ink); min-height: 36px;
            display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ss-rating { font-size: 12px; color: #475569; }
.ss-rating .star { color: #F59E0B; }
.ss-price { font-size: 20px; font-weight: 800; color: var(--navy); letter-spacing: -.01em; }
.ss-mrp { font-size: 12.5px; color: #94A3B8; text-decoration: line-through; }
.ss-off { font-size: 12.5px; color: var(--ok); font-weight: 700; }
.ss-pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 9px; border-radius: 999px;
           font-size: 11.5px; font-weight: 600; width: fit-content; }
.ss-pill .q-icon { font-size: 14px; }
.ss-pill.ok { background: var(--ok-bg); color: var(--ok); }
.ss-pill.warn { background: var(--warn-bg); color: var(--warn); }
.ss-pill.bad { background: var(--bad-bg); color: var(--bad); }
.ss-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.ss-chip { background: #F1F5F9; color: #334155; border-radius: 6px; padding: 1px 7px; font-size: 11.5px; }
.ss-evidence { border-top: 1px dashed var(--line); padding-top: 7px; margin-top: auto; display: flex; flex-direction: column; gap: 3px; }
.ss-ev { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #334155; }
.ss-ev .q-icon { font-size: 15px; }
.ss-ev.verified .q-icon { color: var(--ok); }
.ss-ev.contradicted { color: var(--bad); }
.ss-ev.contradicted .q-icon { color: var(--bad); }
.ss-ev.unknown .q-icon { color: var(--warn); }
.ss-ask { background: #F8FAFC; border: 1px solid var(--line); border-radius: 8px; padding: 6px 8px; font-size: 12px; }
.ss-ask b { color: var(--navy); }
.ss-sku { font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 10.5px; color: #94A3B8; }

/* empty states */
.ss-empty { text-align: center; padding: 42px 20px; }
.ss-empty .q-icon { font-size: 46px; color: #94A3B8; }
.ss-empty h3 { font-size: 19px; font-weight: 700; margin: 10px 0 4px; color: var(--ink); }
.ss-empty p { color: var(--muted); margin: 0; font-size: 14px; }

/* dialog */
.ss-dialog { width: 860px; max-width: 94vw; border-radius: 16px !important; padding: 0 !important; overflow: hidden; }
.ss-spec { display: grid; grid-template-columns: 180px 1fr; border-top: 1px solid var(--line); font-size: 13px; }
.ss-spec div { padding: 7px 0; border-bottom: 1px solid var(--line); }
.ss-spec .k { color: var(--muted); }

/* debug */
.ss-stagebar { display: flex; height: 30px; border-radius: 8px; overflow: hidden; width: 100%; }
.ss-stagebar div { display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11.5px;
                   font-weight: 600; white-space: nowrap; overflow: hidden; }
.ss-metric { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; min-width: 150px; }
.ss-metric .v { font-size: 22px; font-weight: 800; color: var(--navy); }
.ss-metric .l { font-size: 11.5px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }
.ss-debug-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; width: 100%; }
.ss-step { font-size: 15px; font-weight: 700; color: var(--navy); }
.ss-step small { color: var(--muted); font-weight: 500; font-size: 12.5px; margin-left: 6px; }
.ss-footer { color: #94A3B8; font-size: 12px; text-align: center; padding: 18px 0 8px; }
</style>
"""
