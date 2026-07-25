const state = {
  products: new Map(),
  productTotal: 0,
  nextProductOffset: 0,
  hasMoreProducts: true,
  productLoading: false,
  productRequestId: 0,
  productLoadLimit: 12,
  catalogRevision: 0,
  completedFilterKey: '',
  streamedProducts: [],
  streamRenderQueued: false,
  sources: [],
  categories: [],
  stats: {},
  selectedCategory: 'all',
  search: '',
  stockOnly: true,
  minPrice: 0,
  maxPrice: null,
  includeMinPrice: false,
  sort: 'price',
  scanning: false,
  scanTask: { running: false, reason: '', current_source: '', pending_sources: 0 },
  localScanning: false,
  localScanTarget: '',
  autoScanEnabled: false,
  scanIntervalMinutes: 15,
  sourceInterval: 15,
  pendingProducts: new Map(),
  pendingRemovals: new Set(),
  refreshingTags: new Set(),
  refreshTimers: new Map(),
  refreshingProducts: new Set(),
  renderQueued: false,
  history: [],
  historyMode: 'price',
  adminVerified: false,
  serverFullScanStarting: false,
  proxyOnlyScanStarting: false,
  proxyOnlyScanning: false,
  priceaiSyncStarting: false,
  priceaiSyncing: false,
};

const $ = (selector) => document.querySelector(selector);
let searchReloadTimer = 0;
let nextLocalRequestAt = 0;
const LOCAL_REQUEST_COOLDOWN_MS = 1000;
const PRODUCT_CACHE_TTL_MS = 45_000;
const elements = {
  grid: $('#productGrid'), empty: $('#emptyState'), tabs: $('#categoryTabs'),
  total: $('#totalStat'), stock: $('#stockStat'), low: $('#lowStat'), source: $('#sourceStat'),
  sourceSub: $('#sourceStatSub'), result: $('#resultCount'), lastUpdate: $('#lastUpdate'),
  scanPulse: $('#scanPulse'), scanText: $('#scanStateText'),
  localScanButton: $('#localScanButton'), localScanLabel: $('#localScanButton .local-scan-label'),
  filteredLocalScanButton: $('#filteredLocalScanButton'), filteredScanLabel: $('#filteredLocalScanButton .filtered-scan-label'),
  adminTokenInput: $('#adminTokenInput'), adminTokenVerifyButton: $('#adminTokenVerifyButton'),
  adminFullScanButton: $('#adminFullScanButton'),
  adminProxyScanButton: $('#adminProxyScanButton'),
  priceaiSyncButton: $('#priceaiSyncButton'),
  scanDetail: $('#scanDetail'), stream: $('#streamStatus'), dialog: $('#sourceDialog'),
  sourceList: $('#sourceList'), sourceInput: $('#sourceInput'), toast: $('#toast'),
  historyDialog: $('#historyDialog'), historyTitle: $('#historyTitle'), historyShop: $('#historyShop'),
  historyToken: $('#historyToken'), historySummary: $('#historySummary'), historyChart: $('#historyChart'),
  historyModes: $('#historyModes'),
  priceMin: $('#priceMin'), priceMax: $('#priceMax'), includeMinPrice: $('#includeMinPrice'),
  loadMore: $('#loadMoreProducts'), loadMoreButton: $('#loadMoreButton'),
  loadBatchSize: $('#loadBatchSize'), loadMoreStatus: $('#loadMoreStatus'),
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
}[char]));

const money = (value) => Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const dateTime = (timestamp) => timestamp ? new Date(timestamp * 1000).toLocaleString('zh-CN', { hour12: false }) : '尚未扫描';
const relativeTime = (timestamp) => {
  if (!timestamp) return '未知';
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
};

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { elements.toast.className = 'toast'; }, 2800);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try { payload = await response.json(); } catch { /* nginx errors may not be json */ }
  if (!response.ok) {
    const error = new Error(payload.error || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function loadState() {
  try {
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    state.categories = payload.categories || [];
    state.stats = payload.stats || {};
    state.catalogRevision = Number(payload.catalog_revision || 0);
    state.scanning = Boolean(payload.scanning);
    state.scanTask = payload.scan_task || { running: state.scanning };
    state.autoScanEnabled = Boolean(payload.auto_scan_enabled);
    state.scanIntervalMinutes = Math.max(1, Math.round(Number(payload.scan_interval || 900) / 60));
    state.sourceInterval = Number(payload.source_interval || 15);
    updateStats();
    renderTabs();
    renderSources();
    await reloadProducts();
    setScanning(state.scanning, state.scanning ? '正在采集公开店铺' : '自动扫描已关闭');
  } catch (error) {
    toast(error.message, true);
    elements.empty.hidden = false;
  }
}

function categoryCounts() {
  return state.stats.category_counts || {};
}

function renderTabs() {
  const counts = categoryCounts();
  const tabs = [{ key: 'all', label: '全部', count: Number(state.stats.total || 0) }, ...state.categories.map((item) => ({ ...item, count: counts[item.key] || 0 }))];
  elements.tabs.innerHTML = tabs.map((tab) => `
    <span class="category-control">
      <button type="button" class="category ${state.selectedCategory === tab.key ? 'active' : ''} ${state.refreshingTags.has(tab.key) ? 'refreshing' : ''}" data-category="${escapeHtml(tab.key)}" role="tab" aria-selected="${state.selectedCategory === tab.key}" aria-busy="${state.refreshingTags.has(tab.key)}">
        ${escapeHtml(tab.label)} <b>${tab.count}</b><i class="refresh-indicator" title="正在刷新" aria-hidden="true"></i>
      </button>
      <button type="button" class="category-refresh" data-refresh-category="${escapeHtml(tab.key)}" title="用当前网络刷新 ${escapeHtml(tab.label)}" aria-label="用当前网络刷新 ${escapeHtml(tab.label)}" ${state.localScanning ? 'disabled' : ''}>↻</button>
    </span>`).join('');
}

function stopTagRefreshing(key) {
  const timer = state.refreshTimers.get(key);
  if (timer) clearTimeout(timer);
  state.refreshTimers.delete(key);
  state.refreshingTags.delete(key);
  const tab = [...elements.tabs.querySelectorAll('[data-category]')].find((item) => item.dataset.category === key);
  if (tab) {
    tab.classList.remove('refreshing');
    tab.setAttribute('aria-busy', 'false');
  }
}

function markTagsRefreshing(tags = []) {
  for (const key of new Set(['all', ...tags])) {
    const previous = state.refreshTimers.get(key);
    if (previous) clearTimeout(previous);
    state.refreshingTags.add(key);
    const tab = [...elements.tabs.querySelectorAll('[data-category]')].find((item) => item.dataset.category === key);
    if (tab) {
      tab.classList.add('refreshing');
      tab.setAttribute('aria-busy', 'true');
    }
    state.refreshTimers.set(key, setTimeout(() => stopTagRefreshing(key), 900));
  }
}

function clearRefreshingTags() {
  for (const key of [...state.refreshingTags]) stopTagRefreshing(key);
}

function updateTabCounts() {
  const counts = categoryCounts();
  for (const tab of elements.tabs.querySelectorAll('[data-category]')) {
    const key = tab.dataset.category;
    const count = key === 'all' ? Number(state.stats.total || 0) : (counts[key] || 0);
    const badge = tab.querySelector('b');
    if (badge && badge.textContent !== String(count)) badge.textContent = String(count);
  }
}

function productMatchesFilters(product) {
  if (!product?.active) return false;
  if (state.selectedCategory !== 'all' && !(product.tags || []).includes(state.selectedCategory)) return false;
  if (state.stockOnly && !product.in_stock) return false;
  const price = Number(product.price);
  if (!Number.isFinite(price)) return false;
  if (state.includeMinPrice ? price < state.minPrice : price <= state.minPrice) return false;
  if (state.maxPrice !== null && price > state.maxPrice) return false;
  const query = state.search.trim().toLocaleLowerCase();
  return !query || `${product.name} ${product.source_name} ${product.category_name}`.toLocaleLowerCase().includes(query);
}

function compareProducts(a, b) {
  if (state.sort === 'price') {
    return Number(a.price) - Number(b.price)
      || String(a.name).localeCompare(String(b.name), 'zh-CN')
      || String(a.goods_key).localeCompare(String(b.goods_key));
  }
  if (state.sort === 'stock') return Number(b.stock_count) - Number(a.stock_count) || Number(a.price) - Number(b.price);
  return Number(b.changed_at) - Number(a.changed_at) || Number(a.price) - Number(b.price);
}

function filteredProducts() {
  return [...state.products.values()].filter(productMatchesFilters).sort(compareProducts);
}

function currentProductQuery(limit, offset) {
  return new URLSearchParams({
    category: state.selectedCategory,
    stock_only: state.stockOnly ? '1' : '0',
    min_price: String(state.minPrice),
    max_price: state.maxPrice === null ? '' : String(state.maxPrice),
    include_min: state.includeMinPrice ? '1' : '0',
    search: state.search.trim(),
    sort: state.sort,
    limit: String(limit),
    offset: String(offset),
  });
}

function currentFilterMappingKey() {
  return JSON.stringify({
    category: state.selectedCategory,
    stock_only: state.stockOnly,
    min_price: state.minPrice,
    max_price: state.maxPrice,
    include_min: state.includeMinPrice,
    search: state.search.trim().toLocaleLowerCase(),
  });
}

async function readProductStream(params, onRecord) {
  const response = await fetch(`api/products/stream?${params.toString()}`, { cache: 'no-store' });
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch { /* proxy errors may not be json */ }
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('当前浏览器不支持商品流式加载');
  const decoder = new TextDecoder();
  let buffered = '';
  const consume = (final = false) => {
    const lines = buffered.split('\n');
    buffered = final ? '' : lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      onRecord(JSON.parse(line));
    }
    if (final && buffered.trim()) onRecord(JSON.parse(buffered));
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffered += decoder.decode(value, { stream: !done });
      consume(false);
    }
    if (done) break;
  }
  buffered += decoder.decode();
  consume(true);
}

function updateProductLoadingControls() {
  const loaded = state.products.size;
  const total = Number(state.productTotal || 0);
  elements.result.textContent = total ? `已显示 ${loaded} / ${total} 件` : (state.productLoading ? '正在加载…' : '0 件');
  elements.empty.hidden = state.productLoading || total > 0;
  elements.loadMore.hidden = !state.productLoading && !state.hasMoreProducts;
  elements.loadMoreButton.disabled = state.productLoading || !state.hasMoreProducts;
  elements.loadMoreStatus.textContent = state.productLoading
    ? '正在从服务器加载…'
    : state.hasMoreProducts
      ? `还有 ${Math.max(0, total - loaded)} 件可继续加载`
      : `已显示全部 ${total} 件`;
}

function flushStreamedProducts() {
  state.streamRenderQueued = false;
  if (!state.streamedProducts.length) return;
  const fragment = document.createDocumentFragment();
  for (const product of state.streamedProducts.splice(0)) {
    state.products.set(product.goods_key, product);
    const card = findProductCard(product.goods_key);
    if (card) {
      updateProductCard(card, product);
      positionProductCard(card, product);
    } else if (productMatchesFilters(product)) {
      fragment.appendChild(createProductCard(product));
    }
  }
  elements.grid.appendChild(fragment);
  updateProductLoadingControls();
}

function queueStreamedProduct(product) {
  state.streamedProducts.push(product);
  if (state.streamRenderQueued) return;
  state.streamRenderQueued = true;
  requestAnimationFrame(flushStreamedProducts);
}

function productCacheKey(params) {
  return `ldxp-product-stream:${params.toString()}`;
}

function readCachedProductPage(params) {
  try {
    const cached = JSON.parse(localStorage.getItem(productCacheKey(params)) || 'null');
    return cached
      && Number(cached.expires_at) > Date.now()
      && Number(cached.catalog_revision) === state.catalogRevision
      && Array.isArray(cached.records)
      ? cached.records
      : null;
  } catch {
    return null;
  }
}

function cacheProductPage(params, records) {
  try {
    localStorage.setItem(productCacheKey(params), JSON.stringify({
      expires_at: Date.now() + PRODUCT_CACHE_TTL_MS,
      catalog_revision: state.catalogRevision,
      records,
    }));
  } catch {
    // Storage can be unavailable in private mode; the live request still works.
  }
}

function applyProductStreamRecord(record, requestId, offset) {
  if (requestId !== state.productRequestId) return;
  if (record.type === 'meta') {
    state.productTotal = Number(record.total || 0);
    state.catalogRevision = Number(record.catalog_revision || state.catalogRevision);
    state.nextProductOffset = Number(record.next_offset || offset);
    state.hasMoreProducts = Boolean(record.has_more);
    if (!state.hasMoreProducts) state.completedFilterKey = currentFilterMappingKey();
  } else if (record.type === 'product' && record.product) {
    queueStreamedProduct(record.product);
  }
}

async function loadProductBatch() {
  if (state.productLoading || !state.hasMoreProducts) return;
  const requestId = state.productRequestId;
  const offset = state.nextProductOffset;
  const query = currentProductQuery(state.productLoadLimit, offset);
  state.productLoading = true;
  updateProductLoadingControls();
  try {
    const cached = readCachedProductPage(query);
    if (cached) {
      cached.forEach((record) => applyProductStreamRecord(record, requestId, offset));
    } else {
      const records = [];
      await readProductStream(query, (record) => {
        if (record.type !== 'end') records.push(record);
        applyProductStreamRecord(record, requestId, offset);
      });
      if (requestId === state.productRequestId) cacheProductPage(query, records);
    }
  } catch (error) {
    if (requestId === state.productRequestId) toast(error.message, true);
  } finally {
    if (requestId === state.productRequestId) {
      state.productLoading = false;
      if (state.streamRenderQueued) flushStreamedProducts();
      updateProductLoadingControls();
    }
  }
}

async function reloadProducts() {
  state.productRequestId += 1;
  state.products.clear();
  state.productTotal = 0;
  state.nextProductOffset = 0;
  state.hasMoreProducts = true;
  state.completedFilterKey = '';
  state.productLoading = false;
  state.streamedProducts = [];
  elements.grid.replaceChildren();
  updateProductLoadingControls();
  await loadProductBatch();
}

function sortCompletedFilterMapping() {
  const products = [...state.products.values()].sort(compareProducts);
  const fragment = document.createDocumentFragment();
  for (const product of products) fragment.appendChild(createProductCard(product));
  elements.grid.replaceChildren(fragment);
  updateVisibleSummary();
}

function productTags(product) {
  const labels = new Map(state.categories.map((category) => [category.key, category.label]));
  const tagHtml = (product.tags || []).map((tag) => `<span class="tag">${escapeHtml(labels.get(tag) || tag)}</span>`).join('');
  const stockClass = product.in_stock ? 'stock' : 'out';
  const stockLabel = product.stock_count < 0 ? '库存未知' : product.in_stock ? `库存 ${product.stock_count}` : '已缺货';
  return `${tagHtml}<span class="tag ${stockClass}">${stockLabel}</span>`;
}

function marketPrice(product) {
  return Number(product.market_price) > Number(product.price)
    ? `<div class="market-price">参考 ¥${money(product.market_price)}</div>` : '';
}

function productCard(product, index) {
  const image = product.image
    ? `<img class="product-image" src="${escapeHtml(product.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=\'product-image fallback\'>L</span>'">`
    : '<span class="product-image fallback">L</span>';
  const refreshing = state.refreshingProducts.has(product.goods_key);
  return `<article class="product-card${refreshing ? ' product-refreshing' : ''}" data-key="${escapeHtml(product.goods_key)}">
    <a class="product-card-link" href="${escapeHtml(product.link)}" target="_blank" rel="noopener noreferrer" aria-label="查看 ${escapeHtml(product.name)}"></a>
    <button class="product-history" type="button" title="查看价格走势" aria-label="查看 ${escapeHtml(product.name)} 的价格走势"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 17 5-6 4 3 7-9"/></svg></button>
    <button class="product-refresh" type="button" title="只刷新这个商品" aria-label="只刷新 ${escapeHtml(product.name)}" aria-busy="${refreshing}" ${refreshing ? 'disabled' : ''}><span aria-hidden="true">↻</span></button>
    <div class="product-head">${image}<div class="product-title">
      <span class="product-title-link">${escapeHtml(product.name)}</span>
      <div class="shop-line">${escapeHtml(product.source_name || product.source_token)} · ${escapeHtml(product.category_name || product.goods_type)}</div>
    </div></div>
    <div class="tags">${productTags(product)}</div>
    <div class="price-row"><div class="price-block"><div class="price">${money(product.price)}</div><div class="market-slot">${marketPrice(product)}</div></div>
      <div class="product-meta"><span class="stock-number">${escapeHtml(product.source_token)}</span><span class="updated">${relativeTime(product.last_seen)}</span></div>
    </div>
  </article>`;
}

function createProductCard(product) {
  const template = document.createElement('template');
  template.innerHTML = productCard(product, 0).trim();
  return template.content.firstElementChild;
}

function findProductCard(goodsKey) {
  return [...elements.grid.children].find((card) => card.dataset.key === goodsKey) || null;
}

function updateProductCard(card, product) {
  const link = card.querySelector('.product-card-link');
  link.href = product.link;
  link.setAttribute('aria-label', `查看 ${product.name}`);
  const title = card.querySelector('.product-title-link');
  if (title.textContent !== product.name) title.textContent = product.name;
  const refreshButton = card.querySelector('.product-refresh');
  refreshButton.setAttribute('aria-label', `只刷新 ${product.name}`);
  card.querySelector('.product-history').setAttribute('aria-label', `查看 ${product.name} 的价格走势`);
  const shop = card.querySelector('.shop-line');
  const shopText = `${product.source_name || product.source_token} · ${product.category_name || product.goods_type}`;
  if (shop.textContent !== shopText) shop.textContent = shopText;
  card.querySelector('.tags').innerHTML = productTags(product);
  const price = card.querySelector('.price');
  const priceText = money(product.price);
  if (price.textContent !== priceText) price.textContent = priceText;
  card.querySelector('.market-slot').innerHTML = marketPrice(product);
  card.querySelector('.stock-number').textContent = product.source_token;
  card.querySelector('.updated').textContent = relativeTime(product.last_seen);
}

function setProductRefreshing(goodsKey, refreshing) {
  if (refreshing) state.refreshingProducts.add(goodsKey);
  else state.refreshingProducts.delete(goodsKey);
  const card = findProductCard(goodsKey);
  if (!card) return;
  card.classList.toggle('product-refreshing', refreshing);
  const button = card.querySelector('.product-refresh');
  button.disabled = refreshing;
  button.setAttribute('aria-busy', String(refreshing));
}

function applySingleProductRefresh(product) {
  if (!state.products.has(product.goods_key)) return;
  state.products.set(product.goods_key, product);
  let card = findProductCard(product.goods_key);
  if (!productMatchesFilters(product)) {
    card?.remove();
  } else if (card) {
    updateProductCard(card, product);
  } else {
    card = createProductCard(product);
    elements.grid.appendChild(card);
  }
  updateVisibleSummary();
}

function applySingleProductRemoval(goodsKey) {
  if (!state.products.has(goodsKey)) return;
  state.products.delete(goodsKey);
  findProductCard(goodsKey)?.remove();
  updateVisibleSummary();
}

function positionProductCard(card, product) {
  const before = [...elements.grid.children]
    .filter((candidate) => candidate !== card)
    .find((candidate) => {
      const other = state.products.get(candidate.dataset.key);
      return other && compareProducts(product, other) < 0;
    });
  if (before) {
    if (card.nextElementSibling !== before) elements.grid.insertBefore(card, before);
  } else if (card !== elements.grid.lastElementChild) {
    elements.grid.appendChild(card);
  }
}

function reconcileProductCard(product, change) {
  let card = findProductCard(product.goods_key);
  if (!productMatchesFilters(product)) {
    if (card) card.remove();
    return;
  }
  if (!card) {
    card = createProductCard(product);
    elements.grid.appendChild(card);
    positionProductCard(card, product);
    return;
  }
  if (change === 'unchanged') {
    card.querySelector('.updated').textContent = relativeTime(product.last_seen);
    return;
  }
  updateProductCard(card, product);
  positionProductCard(card, product);
}

function updateVisibleSummary() {
  updateProductLoadingControls();
}

function renderProducts() {
  void reloadProducts();
}

function updateStats() {
  const stats = state.stats || {};
  elements.total.textContent = Number(stats.total || 0).toLocaleString('zh-CN');
  elements.stock.textContent = Number(stats.in_stock || 0).toLocaleString('zh-CN');
  elements.low.textContent = Number(stats.lowest_price || 0) > 0 ? `¥${money(stats.lowest_price)}` : '—';
  elements.source.textContent = state.sources.length.toLocaleString('zh-CN');
  elements.sourceSub.textContent = `${state.sources.filter((source) => source.enabled).length} 个已启用`;
  const lastScan = Number(stats.last_scan || 0);
  elements.lastUpdate.textContent = lastScan ? `最近更新 ${dateTime(lastScan)}` : '尚未更新';
}

function updateAdminProxyScanButton() {
  const taskRunning = Boolean(state.scanTask?.running || state.scanning);
  const scanBusy = state.localScanning || state.serverFullScanStarting || state.proxyOnlyScanStarting;
  const allBusy = scanBusy || state.priceaiSyncStarting || state.priceaiSyncing;
  elements.adminTokenVerifyButton.disabled = allBusy;
  elements.adminFullScanButton.disabled = scanBusy || !state.adminVerified;
  elements.adminFullScanButton.classList.toggle('scanning', taskRunning);
  elements.adminFullScanButton.textContent = taskRunning ? '服务器扫描中' : '服务器全量扫描';
  elements.adminProxyScanButton.disabled = scanBusy || !state.adminVerified;
  elements.adminProxyScanButton.classList.toggle('scanning', taskRunning && state.scanTask?.reason === 'manual_proxy_only');
  elements.adminProxyScanButton.textContent = taskRunning && state.scanTask?.reason === 'manual_proxy_only'
    ? '代理扫描中'
    : '代理全量扫描';
  elements.priceaiSyncButton.disabled = state.priceaiSyncStarting || state.priceaiSyncing || !state.adminVerified;
  elements.priceaiSyncButton.classList.toggle('scanning', state.priceaiSyncing);
  elements.priceaiSyncButton.textContent = state.priceaiSyncing ? 'PriceAI 同步中' : '同步 PriceAI';
  if (!state.localScanning) {
    elements.localScanLabel.textContent = state.adminVerified ? '服务器全量扫描' : '本地全部扫描';
    elements.filteredScanLabel.textContent = state.adminVerified ? '服务器刷新筛选' : '刷新当前筛选';
  }
}

function getAdminHeaders() {
  const key = String(elements.adminTokenInput.value || '').trim();
  if (!key) {
    toast('请先输入管理员令牌', true);
    return null;
  }
  sessionStorage.setItem('ldxp-admin-key', key);
  return { 'X-LDXP-Admin-Key': key };
}

function forgetAdminKey(error) {
  if (error?.status !== 403) return;
  state.adminVerified = false;
  sessionStorage.removeItem('ldxp-admin-key');
  elements.adminTokenInput.value = '';
  renderSources();
}

async function verifyAdminToken(quiet = false) {
  const headers = getAdminHeaders();
  if (!headers) return false;
  try {
    await api('api/admin/verify', { method: 'POST', headers });
    state.adminVerified = true;
    if (!quiet) toast('管理员令牌已验证');
    return true;
  } catch (error) {
    forgetAdminKey(error);
    if (!quiet) toast(error.message, true);
    return false;
  } finally {
    updateAdminProxyScanButton();
    renderSources();
  }
}

async function startServerFullScan() {
  if (state.localScanning || state.serverFullScanStarting) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.serverFullScanStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/scan', { method: 'POST', headers });
    state.adminVerified = true;
    state.scanTask = result.task || state.scanTask;
    if (result.started || result.joined) {
      setScanning(true, result.message || '服务器正在流式刷新商品');
      await reloadProducts();
    }
    toast(result.message || '服务器全量扫描已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.serverFullScanStarting = false;
    updateAdminProxyScanButton();
  }
}

async function startAdminProxyScan() {
  if (state.localScanning || state.proxyOnlyScanStarting) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.proxyOnlyScanStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/scan/proxy-only', { method: 'POST', headers });
    state.adminVerified = true;
    state.scanTask = result.task || state.scanTask;
    if (result.started || result.joined) {
      setScanning(true, result.message || '服务器正在流式刷新商品');
      await reloadProducts();
    }
    toast(result.message || '服务器代理扫描已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.proxyOnlyScanStarting = false;
    updateAdminProxyScanButton();
  }
}

async function startPriceaiSync() {
  if (state.priceaiSyncStarting || state.priceaiSyncing) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.priceaiSyncStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/import/priceai', { method: 'POST', headers });
    state.adminVerified = true;
    toast(result.message || 'PriceAI 公开快照同步已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.priceaiSyncStarting = false;
    updateAdminProxyScanButton();
  }
}

function setScanning(scanning, detail = '') {
  state.scanning = scanning;
  const busy = scanning || state.localScanning;
  elements.localScanButton.disabled = state.localScanning;
  elements.filteredLocalScanButton.disabled = state.localScanning;
  elements.scanPulse.classList.toggle('active', busy);
  updateAdminProxyScanButton();
  if (!state.localScanning) {
    elements.scanText.textContent = scanning ? '扫描进行中' : '实时监听中';
    elements.scanDetail.textContent = detail || (scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭'));
  }
}

function setLocalScanning(scanning, detail = '', label = '', target = state.localScanTarget || 'all') {
  state.localScanning = scanning;
  state.localScanTarget = scanning ? target : '';
  const busy = scanning || state.scanning;
  elements.localScanButton.disabled = scanning;
  elements.filteredLocalScanButton.disabled = scanning;
  elements.localScanButton.classList.toggle('scanning', scanning && target === 'all');
  elements.filteredLocalScanButton.classList.toggle('scanning', scanning && target === 'filter');
  for (const button of elements.tabs.querySelectorAll('[data-refresh-category]')) button.disabled = scanning;
  elements.scanPulse.classList.toggle('active', busy);
  updateAdminProxyScanButton();
  elements.localScanLabel.textContent = scanning && target === 'all' ? (label || '本地扫描中') : '本地全部扫描';
  elements.filteredScanLabel.textContent = scanning && target === 'filter' ? (label || '筛选页刷新中') : '刷新当前筛选';
  if (scanning) {
    elements.scanText.textContent = '本地扫描进行中';
    elements.scanDetail.textContent = detail || '正在使用当前设备的网络采集';
  } else {
    elements.scanText.textContent = state.scanning ? '服务器扫描进行中' : '实时监听中';
    elements.scanDetail.textContent = detail || (state.scanning
      ? '服务器后台扫描继续运行'
      : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭'));
  }
}

function scheduleIncrementalRender() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  requestAnimationFrame(() => {
    for (const key of state.pendingRemovals) {
      if (!state.products.has(key)) continue;
      state.products.delete(key);
      findProductCard(key)?.remove();
      if (state.completedFilterKey === currentFilterMappingKey()) state.productTotal = Math.max(0, state.productTotal - 1);
    }
    state.pendingRemovals.clear();
    for (const [key, update] of state.pendingProducts) {
      const existed = state.products.has(key);
      const canAddToCompletedMapping = state.completedFilterKey === currentFilterMappingKey()
        && productMatchesFilters(update.product);
      if (!existed && !canAddToCompletedMapping) continue;
      if (!productMatchesFilters(update.product)) {
        state.products.delete(key);
        findProductCard(key)?.remove();
        if (existed && state.completedFilterKey === currentFilterMappingKey()) state.productTotal = Math.max(0, state.productTotal - 1);
        continue;
      }
      state.products.set(key, update.product);
      reconcileProductCard(update.product, update.change);
      if (!existed && state.completedFilterKey === currentFilterMappingKey()) state.productTotal += 1;
    }
    state.pendingProducts.clear();
    state.renderQueued = false;
    updateVisibleSummary();
  });
}

function queueProduct(product, change = 'changed') {
  const canAddToCompletedMapping = state.completedFilterKey === currentFilterMappingKey()
    && productMatchesFilters(product);
  const streamCurrentServerScan = Boolean(state.scanTask?.running) && productMatchesFilters(product);
  if (!state.products.has(product.goods_key) && !canAddToCompletedMapping && !streamCurrentServerScan) return;
  state.pendingRemovals.delete(product.goods_key);
  state.pendingProducts.set(product.goods_key, { product, change });
  scheduleIncrementalRender();
}

function queueProductRemoval(goodsKey) {
  if (!state.products.has(goodsKey)) return;
  state.pendingProducts.delete(goodsKey);
  state.pendingRemovals.add(goodsKey);
  scheduleIncrementalRender();
}

function connectEvents() {
  const stream = new EventSource('api/events');
  stream.addEventListener('open', () => {
    elements.stream.className = 'stream-status online';
    elements.stream.querySelector('span').textContent = '实时流已连接';
  });
  stream.addEventListener('error', () => {
    elements.stream.className = 'stream-status error';
    elements.stream.querySelector('span').textContent = '连接重试中';
  });
  stream.addEventListener('ready', (event) => {
    const payload = JSON.parse(event.data);
    state.scanning = Boolean(payload.scanning);
    state.scanTask = payload.task || state.scanTask;
    updateAdminProxyScanButton();
  });
  stream.addEventListener('product', (event) => {
    const payload = JSON.parse(event.data);
    markTagsRefreshing(payload.product.tags || []);
    queueProduct(payload.product, payload.change);
  });
  stream.addEventListener('product_remove', (event) => {
    const payload = JSON.parse(event.data);
    markTagsRefreshing(state.products.get(payload.goods_key)?.tags || []);
    queueProductRemoval(payload.goods_key);
  });
  stream.addEventListener('product_refresh', (event) => {
    const payload = JSON.parse(event.data);
    applySingleProductRefresh(payload.product);
  });
  stream.addEventListener('product_refresh_remove', (event) => {
    const payload = JSON.parse(event.data);
    applySingleProductRemoval(payload.goods_key);
  });
  stream.addEventListener('scan_status', (event) => {
    const payload = JSON.parse(event.data);
    state.scanTask = payload.task || state.scanTask;
    if (payload.phase === 'started' && payload.reason === 'manual_proxy_only') state.proxyOnlyScanning = true;
    if (payload.phase === 'completed') state.proxyOnlyScanning = false;
    if (payload.phase === 'started') clearRefreshingTags();
    if (payload.phase === 'completed') setTimeout(clearRefreshingTags, 300);
    setScanning(Boolean(payload.scanning), scanMessage(payload));
  });
  stream.addEventListener('snapshot', (event) => {
    const payload = JSON.parse(event.data);
    const nextRevision = Number(payload.catalog_revision || state.catalogRevision);
    const mappingChanged = nextRevision !== state.catalogRevision;
    state.sources = payload.sources || state.sources;
    state.stats = payload.stats || state.stats;
    state.catalogRevision = nextRevision;
    state.scanTask = payload.scan_task || state.scanTask;
    renderSources();
    updateStats();
    renderTabs();
    if (mappingChanged) void reloadProducts();
  });
  stream.addEventListener('discovery_status', (event) => {
    const payload = JSON.parse(event.data);
    if (payload.phase === 'started') {
      elements.scanDetail.textContent = '正在从公开社区发现新店铺';
    } else if (payload.phase === 'completed') {
      toast(`源发现完成：有效 ${payload.valid} 个，新增 ${payload.added} 个`);
    } else if (payload.phase === 'error') {
      toast(`源发现失败：${payload.error}`, true);
    }
  });
  stream.addEventListener('schedule_status', (event) => {
    const payload = JSON.parse(event.data);
    state.autoScanEnabled = Boolean(payload.enabled);
    state.scanIntervalMinutes = Math.max(1, Math.round(Number(payload.interval || 900) / 60));
    state.sourceInterval = Number(payload.source_interval || 15);
  });
  stream.addEventListener('priceai_sync', (event) => {
    const payload = JSON.parse(event.data);
    state.priceaiSyncing = payload.phase === 'started';
    if (payload.phase === 'completed') {
      toast(`PriceAI 同步完成：${Number(payload.matched || 0)} 件，更新 ${Number(payload.changed || 0)} 件`);
      void loadState();
    } else if (payload.phase === 'error') {
      toast(`PriceAI 同步失败：${payload.error}`, true);
    }
    updateAdminProxyScanButton();
  });
}

function scanMessage(payload) {
  if (payload.phase === 'waiting_for_user') return '正在等待用户刷新写入完成';
  if (payload.phase === 'source_started') return `正在扫描 ${payload.token}（${payload.source_index}/${payload.source_total}）`;
  if (payload.phase === 'source_completed') return `${payload.name || payload.token}：匹配 ${payload.matched} 件`;
  if (payload.phase === 'source_error') return `${payload.token}：${payload.error}`;
  if (payload.phase === 'completed') return '本轮扫描完成';
  return payload.scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭');
}

function renderSources() {
  if (!elements.sourceList || !elements.dialog.open) return;
  if (!state.sources.length) {
    elements.sourceList.innerHTML = '<div class="empty"><strong>还没有采集源</strong></div>';
    return;
  }
  elements.sourceList.innerHTML = state.sources.map((source) => {
    const statusText = { ok: '正常', error: '异常', scanning: '扫描中', pending: '待扫描' }[source.status] || source.status;
    const platform = (() => {
      try { return new URL(source.base_url || LOCAL_LDXP_BASE_URL).hostname; }
      catch { return source.base_url || 'pay.ldxp.cn'; }
    })();
    const entryText = source.entry_goods_key ? ` · 入口商品 ${source.entry_goods_key}` : '';
    const actions = state.adminVerified
      ? `<div class="source-actions"><button type="button" data-action="toggle">${source.enabled ? '停用' : '启用'}</button><button type="button" class="danger" data-action="delete">删除</button></div>`
      : '';
    return `<div class="source-item" data-token="${escapeHtml(source.token)}">
      <div class="source-name"><strong>${escapeHtml(source.name || source.token)}</strong><span>${escapeHtml(platform)} · ${escapeHtml(source.origin || '手动添加')} · ${source.product_count || 0} 件${escapeHtml(entryText)}${source.last_error ? ` · ${escapeHtml(source.last_error)}` : ''}</span></div>
      <span class="source-status ${escapeHtml(source.status)}">${escapeHtml(statusText)}</span>
      ${actions}
    </div>`;
  }).join('');
}

function historySeries(history, mode) {
  const points = [...history].sort((a, b) => Number(a.recorded_at) - Number(b.recorded_at));
  if (mode === 'price') {
    return points
      .filter((point) => Number.isFinite(Number(point.price)) && Number(point.price) >= 0)
      .map((point) => ({ ...point, value: Number(point.price) }));
  }
  return points
    .filter((point) => Number.isFinite(Number(point.stock_count)) && Number(point.stock_count) >= 0)
    .map((point) => ({ ...point, value: Number(point.stock_count) }));
}

function historySvg(history, mode) {
  const points = historySeries(history, mode);
  const labels = { price: '价格', stock: '库存余量' };
  if (!points.length) return `<div class="history-empty">暂无可用${labels[mode]}节点，等待下一次成功刷新。</div>`;

  const width = 760, height = 280;
  const margin = { left: 58, right: 20, top: 20, bottom: 40 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.map((point) => Number(point.value));
  let minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * .12, maximum * .03, .5);
  minimum = Math.max(0, minimum - padding);
  maximum += padding;
  const range = Math.max(.01, maximum - minimum);
  const x = (index) => points.length === 1 ? margin.left + chartWidth / 2 : margin.left + index * chartWidth / (points.length - 1);
  const y = (value) => margin.top + (maximum - value) * chartHeight / range;
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(2)} ${y(Number(point.value)).toFixed(2)}`).join(' ');
  const area = `${path} L ${x(points.length - 1).toFixed(2)} ${margin.top + chartHeight} L ${x(0).toFixed(2)} ${margin.top + chartHeight} Z`;
  const grids = Array.from({ length: 5 }, (_, index) => {
    const value = maximum - index * range / 4;
    const lineY = margin.top + index * chartHeight / 4;
    return `<line x1="${margin.left}" y1="${lineY}" x2="${width - margin.right}" y2="${lineY}"/><text x="${margin.left - 9}" y="${lineY + 4}" text-anchor="end">${Math.round(value)}</text>`;
  }).join('');
  const circles = points.map((point, index) => {
    const value = mode === 'price' ? `¥${money(point.value)}` : Math.round(point.value);
    const detail = mode === 'price' ? `库存 ${escapeHtml(point.stock_count)}` : `价格 ¥${money(point.price)}`;
    return `<circle cx="${x(index)}" cy="${y(Number(point.value))}" r="3"><title>${escapeHtml(dateTime(point.recorded_at))} · ${escapeHtml(labels[mode])} ${value} · ${detail}</title></circle>`;
  }).join('');
  const firstTime = dateTime(points[0].recorded_at);
  const lastTime = dateTime(points[points.length - 1].recorded_at);
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(labels[mode])}随刷新时间变化的折线图">
    <g class="chart-grid">${grids}</g><path class="chart-area ${mode === 'price' ? 'chart-price-area' : ''}" d="${area}"/><path class="chart-line ${mode === 'price' ? 'chart-price-line' : ''}" d="${path}"/><g class="chart-points ${mode === 'price' ? 'chart-price-points' : ''}">${circles}</g>
    <text class="chart-time" x="${margin.left}" y="${height - 12}">${escapeHtml(firstTime)}</text>
    <text class="chart-time" x="${width - margin.right}" y="${height - 12}" text-anchor="end">${escapeHtml(lastTime)}</text>
  </svg>`;
}

function renderHistoryChart() {
  for (const button of elements.historyModes.querySelectorAll('[data-history-mode]')) {
    const active = button.dataset.historyMode === state.historyMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  }
  elements.historyChart.innerHTML = historySvg(state.history, state.historyMode);
}

async function openPriceHistory(goodsKey) {
  const product = state.products.get(goodsKey);
  if (!product) return;
  elements.historyTitle.textContent = product.name;
  elements.historyShop.textContent = product.source_name || product.source_token;
  elements.historyToken.textContent = product.source_token;
  elements.historySummary.innerHTML = '';
  elements.historyChart.innerHTML = '<p>正在加载刷新节点…</p>';
  if (!elements.historyDialog.open) elements.historyDialog.showModal();
  try {
    const payload = await api(`api/history/${encodeURIComponent(goodsKey)}`);
    const history = payload.history || [];
    state.history = history;
    state.historyMode = 'price';
    const prices = history.map((point) => Number(point.price)).filter(Number.isFinite);
    const latest = history[0] || { price: product.price, recorded_at: product.last_seen };
    const lowest = prices.length ? Math.min(...prices) : Number(product.price);
    const highest = prices.length ? Math.max(...prices) : Number(product.price);
    elements.historySummary.innerHTML = `
      <article><span>最新价</span><strong>¥${money(latest.price)}</strong></article>
      <article><span>最低价</span><strong>¥${money(lowest)}</strong></article>
      <article><span>最高价</span><strong>¥${money(highest)}</strong></article>
      <article><span>刷新节点</span><strong>${history.length}</strong></article>`;
    renderHistoryChart();
  } catch (error) {
    elements.historyChart.innerHTML = `<div class="history-empty">${escapeHtml(error.message)}</div>`;
  }
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function joinServerProductRefresh(goodsKey) {
  setProductRefreshing(goodsKey, true);
  toast('服务器正在刷新同店数据，正在接收对应商品更新');
  try {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const payload = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh-status`);
      if (payload.product) applySingleProductRefresh(payload.product);
      if (!payload.refreshing) return;
      await delay(1500);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    setProductRefreshing(goodsKey, false);
  }
}

async function refreshProductOnServer(goodsKey) {
  const headers = getAdminHeaders();
  if (!headers) return false;
  setProductRefreshing(goodsKey, true);
  try {
    const result = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh`, {
      method: 'POST',
      headers,
    });
    state.adminVerified = true;
    if (result.joined) {
      await joinServerProductRefresh(goodsKey);
      return true;
    }
    if (result.product) applySingleProductRefresh(result.product);
    if (result.removed) applySingleProductRemoval(goodsKey);
    toast(result.message || '服务器已刷新该商品');
    return true;
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
    return false;
  } finally {
    setProductRefreshing(goodsKey, false);
    updateAdminProxyScanButton();
  }
}

async function refreshProduct(goodsKey) {
  if (!goodsKey || state.refreshingProducts.has(goodsKey) || state.localScanning) return;
  const product = state.products.get(goodsKey);
  if (!product) return;
  const source = state.sources.find((item) => item.token === product.source_token);
  if (source?.source_kind !== 'shop_api') {
    toast('该商品由 PriceAI 快照维护，请使用同步 PriceAI 更新', true);
    return;
  }
  if (state.adminVerified) {
    await refreshProductOnServer(goodsKey);
    return;
  }
  try {
    const status = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh-status`);
    if (status.refreshing) {
      await joinServerProductRefresh(goodsKey);
      return;
    }
  } catch (error) {
    toast(error.message, true);
    return;
  }
  setProductRefreshing(goodsKey, true);
  setLocalScanning(true, `正在用当前设备刷新 ${product.name}`, '刷新单件 1/1', 'filter');
  try {
    const result = await refreshLocalProducts([product]);
    toast(result.failed ? '本地刷新失败，请检查当前网络后重试' : '商品已通过当前设备刷新', result.failed > 0);
    await loadState();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setProductRefreshing(goodsKey, false);
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'filter');
  }
}

const LOCAL_LDXP_BASE_URL = 'https://pay.ldxp.cn';
const LOCAL_GOODS_TYPES = ['card', 'article', 'resource', 'equity'];
const LOCAL_PAGE_SIZE = 300;
const LOCAL_MAX_PAGES = 20;

function sourceBaseUrl(source) {
  return String(source?.base_url || LOCAL_LDXP_BASE_URL).replace(/\/$/, '');
}

function sourceRemoteToken(source) {
  return String(source?.remote_token || source?.token || '');
}

async function localMarketplacePost(baseUrl, path, fields) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  let response;
  try {
    response = await fetch(`${String(baseUrl).replace(/\/$/, '')}${path}`, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      headers: { Accept: 'application/json, text/plain, */*' },
      body: new URLSearchParams(Object.entries(fields).map(([key, value]) => [key, value ?? ''])),
      signal: controller.signal,
    });
  } catch (error) {
    const reason = error.name === 'AbortError' ? '请求超时' : '本机网络或浏览器跨域拦截';
    throw new Error(`${reason}：${error.message}`);
  } finally {
    clearTimeout(timeout);
  }

  const text = await response.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(`采集站点未返回 JSON（HTTP ${response.status}）`);
  }
  if (!response.ok) throw new Error(payload.msg || `采集站点请求失败 (${response.status})`);
  if (payload.code !== 1) throw new Error(payload.msg || '采集站点返回未知错误');
  return payload.data;
}

function compactLocalItem(item, goodsType) {
  const text = (value, limit) => String(value ?? '').slice(0, limit);
  return {
    goods_key: text(item.goods_key, 200),
    name: text(item.name, 500),
    price: item.price,
    market_price: item.market_price,
    extend: { stock_count: item.extend?.stock_count },
    category: { name: text(item.category?.name, 300) },
    goods_type: text(item.goods_type || goodsType, 50),
    link: text(item.link, 2000),
    image: text(item.image, 2000),
    description: text(item.description, 1000),
    create_time: item.create_time,
  };
}

async function collectLocalSource(source) {
  if (source?.source_kind !== 'shop_api') {
    throw new Error('该来源不是可本地扫描的店铺 API');
  }
  const baseUrl = sourceBaseUrl(source);
  const remoteToken = sourceRemoteToken(source);
  const shop = await localMarketplacePost(baseUrl, '/shopApi/Shop/info', { token: remoteToken });
  let goodsTypes = LOCAL_GOODS_TYPES.filter((type) => Number(shop?.[`${type}_count`] || 0) > 0);
  if (!goodsTypes.length) goodsTypes = [...LOCAL_GOODS_TYPES];

  const items = new Map();
  for (const goodsType of goodsTypes) {
    for (let page = 1; page <= LOCAL_MAX_PAGES; page += 1) {
      const payload = await localMarketplacePost(baseUrl, '/shopApi/Shop/goodsList', {
        token: remoteToken,
        keywords: '',
        category_id: 0,
        goods_type: goodsType,
        current: page,
        pageSize: LOCAL_PAGE_SIZE,
      });
      const pageItems = Array.isArray(payload?.list) ? payload.list : [];
      for (const item of pageItems) {
        const compact = compactLocalItem(item, goodsType);
        if (compact.goods_key) items.set(compact.goods_key, compact);
      }
      const total = Number(payload?.total ?? pageItems.length);
      if (!pageItems.length || page * LOCAL_PAGE_SIZE >= total || pageItems.length < LOCAL_PAGE_SIZE) break;
      if (page === LOCAL_MAX_PAGES) throw new Error(`商品超过 ${LOCAL_PAGE_SIZE * LOCAL_MAX_PAGES} 条，本轮未覆盖全部数据`);
    }
  }
  const entryGoodsKey = String(source.entry_goods_key || '').trim();
  if (entryGoodsKey && !items.has(entryGoodsKey)) {
    const item = await localMarketplacePost(
      baseUrl,
      '/shopApi/Shop/goodsInfo',
      { goods_key: entryGoodsKey },
    );
    const compact = compactLocalItem(item, item?.goods_type || '');
    if (compact.goods_key) items.set(compact.goods_key, compact);
  }
  return {
    sourceName: String(shop?.nickname || source.name || source.token).slice(0, 200),
    items: [...items.values()],
  };
}

function groupLocalProducts(products) {
  const sources = new Map();
  for (const product of products) {
    if (!product?.source_token || !product?.goods_key) continue;
    if (!sources.has(product.source_token)) {
      const configuredSource = state.sources.find((item) => item.token === product.source_token);
      sources.set(product.source_token, {
        token: product.source_token,
        sourceName: product.source_name || product.source_token,
        baseUrl: sourceBaseUrl(configuredSource),
        remoteToken: sourceRemoteToken(configuredSource) || product.source_token,
        entryGoodsKey: String(configuredSource?.entry_goods_key || ''),
        types: new Map(),
        untyped: [],
      });
    }
    const source = sources.get(product.source_token);
    const goodsType = String(product.goods_type || '').trim();
    if (!goodsType) {
      source.untyped.push(product);
      continue;
    }
    if (!source.types.has(goodsType)) source.types.set(goodsType, []);
    source.types.get(goodsType).push(product);
  }
  return [...sources.values()];
}

async function collectLocalProductGroup(source, goodsType, products) {
  const targets = new Set(products.map((product) => String(product.goods_key)));
  const found = new Map();
  for (let page = 1; page <= LOCAL_MAX_PAGES; page += 1) {
    const payload = await localMarketplacePost(source.baseUrl, '/shopApi/Shop/goodsList', {
      token: source.remoteToken,
      keywords: '',
      category_id: 0,
      goods_type: goodsType,
      current: page,
      pageSize: LOCAL_PAGE_SIZE,
    });
    const pageItems = Array.isArray(payload?.list) ? payload.list : [];
    for (const item of pageItems) {
      const goodsKey = String(item?.goods_key || '');
      if (targets.has(goodsKey)) found.set(goodsKey, compactLocalItem(item, goodsType));
    }
    const total = Number(payload?.total ?? pageItems.length);
    if (!pageItems.length || page * LOCAL_PAGE_SIZE >= total || pageItems.length < LOCAL_PAGE_SIZE) break;
    if (page === LOCAL_MAX_PAGES) throw new Error(`商品超过 ${LOCAL_PAGE_SIZE * LOCAL_MAX_PAGES} 条，未安全覆盖 ${goodsType}`);
  }
  if (targets.has(source.entryGoodsKey) && !found.has(source.entryGoodsKey)) {
    const item = await localMarketplacePost(
      source.baseUrl,
      '/shopApi/Shop/goodsInfo',
      { goods_key: source.entryGoodsKey },
    );
    if (item?.goods_key) {
      found.set(String(item.goods_key), compactLocalItem(item, item.goods_type || goodsType));
    }
  }
  return { requestedKeys: [...targets], items: [...found.values()] };
}

async function collectLocalUntypedProducts(products) {
  const requestedKeys = [];
  const items = [];
  let failed = 0;
  for (const product of products) {
    try {
      const source = state.sources.find((value) => value.token === product.source_token);
      const item = await localMarketplacePost(
        sourceBaseUrl(source),
        '/shopApi/Shop/goodsInfo',
        { goods_key: product.goods_key },
      );
      requestedKeys.push(product.goods_key);
      if (item?.goods_key) items.push(compactLocalItem(item, item.goods_type || ''));
    } catch (error) {
      failed += 1;
      console.warn(`Local product refresh failed for ${product.goods_key}:`, error);
    }
  }
  return { requestedKeys, items, failed };
}

async function refreshLocalProducts(products, onProgress = null) {
  const sources = groupLocalProducts(products);
  let completed = 0;
  let failed = 0;
  let matched = 0;
  let requested = 0;

  for (let sourceIndex = 0; sourceIndex < sources.length; sourceIndex += 1) {
    const source = sources[sourceIndex];
    onProgress?.(source, sourceIndex + 1, sources.length);
    const requestedKeys = new Set();
    const items = new Map();

    for (const [goodsType, groupProducts] of source.types) {
      try {
        const group = await collectLocalProductGroup(source, goodsType, groupProducts);
        for (const key of group.requestedKeys) requestedKeys.add(key);
        for (const item of group.items) items.set(item.goods_key, item);
      } catch (error) {
        failed += 1;
        console.warn(`Local filtered scan failed for ${source.token}/${goodsType}:`, error);
      }
    }

    if (source.untyped.length) {
      const group = await collectLocalUntypedProducts(source.untyped);
      for (const key of group.requestedKeys) requestedKeys.add(key);
      for (const item of group.items) items.set(item.goods_key, item);
      failed += group.failed;
    }

    if (!requestedKeys.size) continue;
    try {
      const result = await api('api/local-scan/products', {
        method: 'POST',
        body: JSON.stringify({
          token: source.token,
          source_name: source.sourceName,
          items: [...items.values()],
          requested_keys: [...requestedKeys],
        }),
      });
      completed += 1;
      matched += Number(result.matched || 0);
      requested += requestedKeys.size;
    } catch (error) {
      failed += 1;
      console.warn(`Local filtered upload failed for ${source.token}:`, error);
    }
  }
  return { completed, failed, matched, requested };
}

async function localFilteredScan(scopeLabel = '当前筛选') {
  if (state.localScanning) return;
  if (state.adminVerified) {
    await startServerFullScan();
    return;
  }
  setLocalScanning(true, `正在读取${scopeLabel}结果`, '筛选读取中', 'filter');
  try {
    const products = await loadAllFilteredProducts((loaded, total) => {
      setLocalScanning(
        true,
        `正在读取${scopeLabel}结果（${loaded}/${total || '…'}）`,
        '筛选读取中',
        'filter',
      );
    });
    if (!products.length) {
      toast(`${scopeLabel}没有可刷新的商品`, true);
      return;
    }
    setLocalScanning(true, `准备刷新${scopeLabel}的 ${products.length} 件商品`, '筛选刷新 0%', 'filter');
    const result = await refreshLocalProducts(products, (source, current, total) => {
      setLocalScanning(
        true,
        `正在用当前设备刷新 ${source.sourceName}`,
        `筛选刷新 ${current}/${total}`,
        'filter',
      );
    });
    toast(`${scopeLabel}刷新完成：提交 ${result.requested} 件，匹配 ${result.matched} 件，失败 ${result.failed} 组`, result.failed > 0);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'filter');
    await loadState();
  }
}

async function loadAllFilteredProducts(onProgress) {
  const products = [];
  let offset = 0;
  let total = 0;
  while (true) {
    let nextOffset = offset;
    await readProductStream(currentProductQuery(500, offset), (record) => {
      if (record.type === 'meta') {
        total = Number(record.total || 0);
        nextOffset = Number(record.next_offset || offset);
      } else if (record.type === 'product' && record.product) {
        products.push(record.product);
        onProgress?.(products.length, total);
      }
    });
    if (!total || nextOffset >= total || nextOffset <= offset) break;
    offset = nextOffset;
  }
  return products;
}

async function localManualScan() {
  if (state.localScanning) return;
  if (state.adminVerified) {
    await startServerFullScan();
    return;
  }
  const sources = state.sources.filter(
    (source) => source.enabled && source.source_kind === 'shop_api'
  );
  if (!sources.length) {
    toast('没有已启用的采集源', true);
    return;
  }

  let succeeded = 0;
  let failed = 0;
  let matched = 0;
  setLocalScanning(true, '准备使用当前设备的网络', `本地扫描 0/${sources.length}`, 'all');
  try {
    for (let index = 0; index < sources.length; index += 1) {
      const source = sources[index];
      setLocalScanning(true, `正在本地扫描 ${source.name || source.token}`, `本地扫描 ${index + 1}/${sources.length}`, 'all');
      try {
        const collected = await collectLocalSource(source);
        const result = await api('api/local-scan/source', {
          method: 'POST',
          body: JSON.stringify({
            token: source.token,
            source_name: collected.sourceName,
            items: collected.items,
            complete: true,
          }),
        });
        succeeded += 1;
        matched += Number(result.matched || 0);
      } catch (error) {
        failed += 1;
        console.warn(`Local scan failed for ${source.token}:`, error);
      }
    }
    toast(`本地扫描完成：成功 ${succeeded} 店，失败 ${failed} 店，匹配 ${matched} 件`, failed > 0);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'all');
    await loadState();
  }
}

function openSources() {
  if (!elements.dialog.open) elements.dialog.showModal();
  renderSources();
}

function applyPriceRange() {
  const minimum = Number(elements.priceMin.value || 0);
  const maximumText = elements.priceMax.value.trim();
  const maximum = maximumText === '' ? null : Number(maximumText);
  if (!Number.isFinite(minimum) || minimum < 0 || (maximum !== null && (!Number.isFinite(maximum) || maximum < 0))) {
    toast('价格范围必须是非负数字', true);
    return;
  }
  if (maximum !== null && maximum < minimum) {
    toast('最高价格不能低于最低价格', true);
    return;
  }
  state.minPrice = minimum;
  state.maxPrice = maximum;
  state.includeMinPrice = elements.includeMinPrice.checked;
  renderProducts();
}

document.addEventListener('click', (event) => {
  const historyButton = event.target.closest('.product-history');
  if (historyButton) {
    event.preventDefault();
    event.stopPropagation();
    openPriceHistory(historyButton.closest('.product-card')?.dataset.key);
    return;
  }
  const refreshButton = event.target.closest('.product-refresh');
  if (refreshButton) {
    event.preventDefault();
    event.stopPropagation();
    refreshProduct(refreshButton.closest('.product-card')?.dataset.key);
    return;
  }
  const tab = event.target.closest('[data-category]');
  const refreshCategory = event.target.closest('[data-refresh-category]');
  if (refreshCategory) {
    const category = refreshCategory.dataset.refreshCategory;
    const label = category === 'all'
      ? '全部商品'
      : state.categories.find((item) => item.key === category)?.label || category;
    state.selectedCategory = category;
    renderTabs();
    renderProducts();
    void localFilteredScan(label);
    return;
  }
  if (tab) {
    state.selectedCategory = tab.dataset.category;
    renderTabs(); renderProducts();
  }
});

$('#searchInput').addEventListener('input', (event) => {
  state.search = event.target.value;
  clearTimeout(searchReloadTimer);
  searchReloadTimer = setTimeout(() => renderProducts(), 220);
});
$('#stockOnly').addEventListener('change', (event) => { state.stockOnly = event.target.checked; renderProducts(); });
elements.priceMin.addEventListener('change', applyPriceRange);
elements.priceMax.addEventListener('change', applyPriceRange);
elements.includeMinPrice.addEventListener('change', applyPriceRange);
$('#sortSelect').addEventListener('change', (event) => {
  state.sort = event.target.value;
  if (state.completedFilterKey === currentFilterMappingKey()) {
    sortCompletedFilterMapping();
  } else {
    renderProducts();
  }
});
elements.loadBatchSize.addEventListener('change', (event) => {
  state.productLoadLimit = Number(event.target.value) || 12;
});
elements.loadMoreButton.addEventListener('click', () => { void loadProductBatch(); });
elements.localScanButton.addEventListener('click', localManualScan);
elements.filteredLocalScanButton.addEventListener('click', () => { void localFilteredScan(); });
elements.adminTokenVerifyButton.addEventListener('click', () => { void verifyAdminToken(); });
elements.adminTokenInput.addEventListener('input', () => {
  state.adminVerified = false;
  updateAdminProxyScanButton();
  renderSources();
});
elements.adminFullScanButton.addEventListener('click', () => { void startServerFullScan(); });
elements.adminProxyScanButton.addEventListener('click', () => { void startAdminProxyScan(); });
elements.priceaiSyncButton.addEventListener('click', () => { void startPriceaiSync(); });
elements.historyModes.addEventListener('click', (event) => {
  const button = event.target.closest('[data-history-mode]');
  if (!button) return;
  state.historyMode = button.dataset.historyMode;
  renderHistoryChart();
});
$('#sourceButton').addEventListener('click', () => openSources());

$('#addSourceForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const result = await api('api/sources', {
      method: 'POST',
      body: JSON.stringify({ source: elements.sourceInput.value.trim() }),
    });
    elements.sourceInput.value = '';
    toast(result.scan_queued ? '采集源已加入，服务器正在扫描' : '采集源已加入，等待服务器扫描');
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    state.stats = payload.stats || state.stats;
    renderSources(); updateStats();
  } catch (error) { toast(error.message, true); }
});

elements.sourceList.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  const item = event.target.closest('.source-item');
  if (!button || !item) return;
  const token = item.dataset.token;
  const source = state.sources.find((value) => value.token === token);
  if (!source || !state.adminVerified) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  try {
    if (button.dataset.action === 'delete') {
      if (!confirm(`确认删除采集源 ${token}？对应的本地商品记录也会删除。`)) return;
      await api(`api/sources/${encodeURIComponent(token)}`, { method: 'DELETE', headers });
    } else {
      await api(`api/sources/${encodeURIComponent(token)}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ enabled: !source.enabled }),
      });
    }
    await loadState();
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  }
});

const savedAdminToken = sessionStorage.getItem('ldxp-admin-key') || '';
if (savedAdminToken) {
  elements.adminTokenInput.value = savedAdminToken;
  void verifyAdminToken(true);
}
updateAdminProxyScanButton();
loadState();
connectEvents();
setInterval(() => {
  for (const card of document.querySelectorAll('.product-card .updated')) {
    const product = state.products.get(card.closest('.product-card')?.dataset.key);
    if (product) card.textContent = relativeTime(product.last_seen);
  }
}, 60000);
