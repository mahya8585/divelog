<template>
  <div class="d-flex flex-column min-vh-100">
    <nav class="navbar navbar-dark bg-ocean py-2">
      <div class="container">
        <router-link class="navbar-brand fw-bold" to="/">
          <i class="bi bi-water me-2"></i>Dive Log
        </router-link>
      </div>
    </nav>

    <main class="flex-grow-1">
      <router-view />
    </main>

    <footer class="bg-ocean text-white text-center py-3 mt-4">
      <small><i class="bi bi-water me-1"></i>Dive Log</small>
    </footer>
  </div>
</template>

<style>
/* ── CSS 変数 ─────────────────────────────────────────── */
:root {
  --ocean-dark: #0a1628;
  --ocean-mid:  #1a5f8a;
  --ocean-teal: #00b4d8;
  --coral:      #ff6b6b;
  --bg:         #f0f7fc;
}

body {
  background: var(--bg);
  font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
}

/* ── Navbar / Footer ─────────────────────────────────── */
.bg-ocean {
  background: linear-gradient(135deg, var(--ocean-dark), var(--ocean-mid)) !important;
}

/* ── マップ ──────────────────────────────────────────── */
.map-container    { height: 480px; }
.map-container-sm { height: 220px; }

/* ── 検索カード ──────────────────────────────────────── */
.search-card {
  border: none;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 12px rgba(0,0,0,.08);
}

/* ── ダイブカード ─────────────────────────────────────── */
.dive-card {
  display: block;
  background: #fff;
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin-bottom: .75rem;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
  color: inherit;
  text-decoration: none;
  transition: transform .15s, box-shadow .15s;
}
.dive-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,180,216,.2);
  color: inherit;
}

/* ── ダイブ番号サークル ───────────────────────────────── */
.dive-number-circle {
  width: 48px; height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--ocean-teal), var(--ocean-mid));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: .95rem;
  flex-shrink: 0;
}

/* ── タグバッジ ──────────────────────────────────────── */
.tag-badge {
  display: inline-block;
  background: linear-gradient(135deg, var(--ocean-teal), var(--ocean-mid));
  color: #fff !important;
  border-radius: 20px;
  padding: .2em .75em;
  font-size: .8rem;
  text-decoration: none;
  margin: .1rem .15rem;
}
.tag-badge:hover { opacity: .85; }

/* ── スタットタイル ───────────────────────────────────── */
.stat-tile {
  background: #fff;
  border-radius: 10px;
  padding: .75rem 1rem;
  text-align: center;
  box-shadow: 0 1px 6px rgba(0,0,0,.07);
}
.stat-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--ocean-mid);
  line-height: 1.1;
}

/* ── セクションカード ─────────────────────────────────── */
.section-card {
  background: #fff;
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
  margin-bottom: 1rem;
}
.section-title {
  font-size: .8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--ocean-teal);
  border-bottom: 2px solid var(--ocean-teal);
  padding-bottom: .3rem;
  margin-bottom: .85rem;
}

/* ── ギアロー ────────────────────────────────────────── */
.gear-row   { display: flex; gap: .5rem; margin-bottom: .35rem; font-size: .9rem; }
.gear-label { color: #888; min-width: 110px; flex-shrink: 0; }

/* ── チャートコンテナ ─────────────────────────────────── */
.chart-container { height: 280px; }

/* ── メモボックス ────────────────────────────────────── */
.memo-box {
  background: #f8fcff;
  border-left: 4px solid var(--ocean-teal);
  border-radius: 0 8px 8px 0;
  padding: .85rem 1rem;
  font-size: .93rem;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 戻るボタン ──────────────────────────────────────── */
.btn-back {
  color: var(--ocean-mid);
  border: 1.5px solid var(--ocean-mid);
  border-radius: 20px;
  padding: .25rem .9rem;
  font-size: .85rem;
  background: transparent;
  text-decoration: none;
}
.btn-back:hover {
  background: var(--ocean-mid);
  color: #fff;
}
</style>
