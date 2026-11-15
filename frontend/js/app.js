/* 半导体可靠性计算平台 —— 前端交互 */
(function () {
  "use strict";

  const state = {
    token: localStorage.getItem("semirel_token") || null,
    user: null,
    quota: null,
    calculators: [],
    current: null,
    currentResult: null,
    chart: null,
    authMode: "login",
    recordToLoad: null,
  };

  const CHART_COLORS = ["#0f2a47", "#14a08f", "#c47f17", "#2f7bbd", "#8a9bb0"];

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

  /* ------------------------------------------------------------------ 工具 */
  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatNumber(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "string") return value;
    const num = Number(value);
    if (!Number.isFinite(num)) return String(value);
    if (num === 0) return "0";
    const abs = Math.abs(num);
    if (abs >= 1e6) return num.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
    if (abs < 1e-3) return num.toExponential(2);
    return num.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }

  function toast(message, type) {
    const tone = type || "success";
    const host = $("#toast-container");
    const wrapper = document.createElement("div");
    wrapper.className = "toast align-items-center text-bg-" + tone + " border-0";
    wrapper.setAttribute("role", "status");
    wrapper.innerHTML =
      '<div class="d-flex"><div class="toast-body">' + esc(message) +
      '</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    host.appendChild(wrapper);
    const instance = new bootstrap.Toast(wrapper, { delay: 3200 });
    instance.show();
    wrapper.addEventListener("hidden.bs.toast", () => wrapper.remove());
  }

  function parseError(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg || JSON.stringify(item)).join("；");
    }
    return fallback;
  }

  async function api(path, options) {
    const opts = options || {};
    const headers = Object.assign({}, opts.headers || {});
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (state.token) headers["Authorization"] = "Bearer " + state.token;

    const response = await fetch(path, Object.assign({}, opts, { headers }));
    if (!response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch (err) { /* 非 JSON 响应 */ }
      if (response.status === 401) {
        state.token = null;
        localStorage.removeItem("semirel_token");
      }
      throw new Error(parseError(payload, response.status + " " + response.statusText));
    }
    if (response.status === 204) return null;
    return response.json();
  }

  async function downloadRequest(url, body) {
    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    const response = await fetch(url, {
      method: body ? "POST" : "GET",
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch (err) { /* ignore */ }
      throw new Error(parseError(payload, "导出失败（" + response.status + "）"));
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = match ? match[1] : "reliability_export";
    const blob = await response.blob();
    const link = document.createElement("a");
    const objectUrl = URL.createObjectURL(blob);
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
  }

  /* -------------------------------------------------------------- 视图切换 */
  const VIEWS = ["home", "calculator", "history", "about"];

  function setView(view) {
    VIEWS.forEach((name) => {
      const section = $("#view-" + name);
      if (section) section.classList.toggle("d-none", name !== view);
    });
    const hero = $(".hero");
    if (hero) hero.classList.toggle("d-none", view !== "home");
    $$(".app-navbar .nav-link").forEach((link) => {
      link.classList.toggle("active", link.dataset.view === view);
    });
    if (view === "history") loadHistory();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* -------------------------------------------------------------- 计算器列表 */
  const CALC_ICONS = { mtbf: "bi-activity", duane: "bi-graph-up", sample_size: "bi-clipboard-data" };

  function renderCalculatorGrid() {
    const grid = $("#calculator-grid");
    if (!state.calculators.length) {
      grid.innerHTML = '<div class="col-12"><div class="alert alert-danger mb-0">计算器列表为空，请检查后端服务。</div></div>';
      return;
    }
    grid.innerHTML = state.calculators.map((calc) => {
      const standards = (calc.standards || [])
        .map((std) => '<span class="badge std-badge">' + esc(std) + "</span>")
        .join(" ");
      return (
        '<div class="col-md-6 col-xl-4">' +
          '<div class="calc-card">' +
            '<div class="card-body">' +
              '<div class="d-flex align-items-center gap-3">' +
                '<span class="calc-icon"><i class="bi ' + (CALC_ICONS[calc.id] || "bi-calculator") + '"></i></span>' +
                '<div><h3>' + esc(calc.name) + '</h3><span class="text-muted small">' + esc(calc.category) + "</span></div>" +
              "</div>" +
              '<p class="calc-desc mt-2">' + esc(calc.description) + "</p>" +
              '<div class="calc-formula">' + esc(calc.formula_summary) + "</div>" +
              '<div class="d-flex flex-wrap gap-1 mt-1">' + standards + "</div>" +
              '<button class="btn btn-primary mt-2 w-100" type="button" data-open-calc="' + esc(calc.id) + '">' +
                '开始计算 <i class="bi bi-arrow-right"></i></button>' +
            "</div>" +
          "</div>" +
        "</div>"
      );
    }).join("");

    $$("[data-open-calc]").forEach((button) => {
      button.addEventListener("click", () => openCalculator(button.dataset.openCalc));
    });
  }

  /* -------------------------------------------------------------- 表单渲染 */
  function fieldControl(field, value) {
    const id = "field-" + field.name;
    const common = 'class="form-control" id="' + id + '" name="' + field.name + '"';
    if (field.type === "select") {
      const options = (field.options || []).map((option) => {
        const selected = String(value) === String(option.value) ? " selected" : "";
        return '<option value="' + esc(option.value) + '"' + selected + ">" + esc(option.label) + "</option>";
      }).join("");
      return '<select class="form-select" id="' + id + '" name="' + field.name + '">' + options + "</select>";
    }
    if (field.type === "text") {
      return '<textarea ' + common + ' rows="2" placeholder="' + esc(field.placeholder || "") + '">' +
        esc(value === undefined || value === null ? "" : value) + "</textarea>";
    }
    const step = field.step !== null && field.step !== undefined ? field.step : (field.type === "integer" ? 1 : "any");
    const min = field.min !== null && field.min !== undefined ? ' min="' + field.min + '"' : "";
    const max = field.max !== null && field.max !== undefined ? ' max="' + field.max + '"' : "";
    const inputMode = field.type === "integer" ? ' inputmode="numeric"' : ' inputmode="decimal"';
    const raw = value === undefined || value === null ? "" : value;
    return '<input type="number" ' + common + ' value="' + esc(raw) + '" step="' + step + '"' + min + max + inputMode +
      ' placeholder="' + esc(field.placeholder || "") + '">';
  }

  function renderForm(info, prefill) {
    const form = $("#calc-form");
    const source = prefill || {};
    form.innerHTML = info.input_fields.map((field) => {
      const value = Object.prototype.hasOwnProperty.call(source, field.name) ? source[field.name] : field.default;
      const required = field.required ? '<span class="text-danger ms-1">*</span>' : "";
      const unit = field.unit ? '<span class="unit">(' + esc(field.unit) + ")</span>" : "";
      const help = field.description ? '<div class="form-text">' + esc(field.description) + "</div>" : "";
      return (
        '<div class="field-group" data-field="' + esc(field.name) + '">' +
          '<label class="form-label" for="field-' + esc(field.name) + '">' + esc(field.label) + unit + required + "</label>" +
          fieldControl(field, value) +
          help +
        "</div>"
      );
    }).join("");

    $$("#calc-form input, #calc-form select, #calc-form textarea").forEach((input) => {
      input.addEventListener("change", updateVisibility);
    });
    updateVisibility();
  }

  function updateVisibility() {
    if (!state.current) return;
    const form = $("#calc-form");
    state.current.input_fields.forEach((field) => {
      if (!field.visible_when) return;
      const controller = form.querySelector('[name="' + field.visible_when.field + '"]');
      const group = form.querySelector('.field-group[data-field="' + field.name + '"]');
      if (!controller || !group) return;
      const allowed = (field.visible_when.values || []).map(String);
      const visible = allowed.indexOf(String(controller.value)) !== -1;
      group.classList.toggle("conditional-hidden", !visible);
      $$("input, select, textarea", group).forEach((element) => {
        element.disabled = !visible;
      });
    });
  }

  function fillForm(values) {
    if (!state.current) return;
    state.current.input_fields.forEach((field) => {
      const control = $('#calc-form [name="' + field.name + '"]');
      if (!control) return;
      if (Object.prototype.hasOwnProperty.call(values, field.name) && values[field.name] !== undefined && values[field.name] !== null) {
        control.value = values[field.name];
      }
    });
    updateVisibility();
  }

  function collectInputs() {
    const inputs = {};
    state.current.input_fields.forEach((field) => {
      const control = $('#calc-form [name="' + field.name + '"]');
      if (!control || control.disabled) return;
      const raw = String(control.value || "").trim();
      if (raw === "") {
        if (field.required) throw new Error("请填写「" + field.label + "」");
        return;
      }
      if (field.type === "number" || field.type === "integer") {
        const num = Number(raw);
        if (!Number.isFinite(num)) throw new Error("「" + field.label + "」必须是数字");
        if (field.type === "integer" && !Number.isInteger(num)) throw new Error("「" + field.label + "」必须是整数");
        inputs[field.name] = num;
      } else {
        inputs[field.name] = raw;
      }
    });
    return inputs;
  }

  /* -------------------------------------------------------------- 打开计算器 */
  function openCalculator(id, prefill, preset) {
    const info = state.calculators.find((item) => item.id === id);
    if (!info) {
      toast("未找到该计算器", "danger");
      return;
    }
    state.current = info;
    state.currentResult = null;
    $("#calc-title").textContent = info.name;
    $("#calc-desc").textContent = info.description;
    $("#calc-category").textContent = info.category;
    $("#calc-standards").textContent = info.standards && info.standards.length
      ? "方法出处：" + info.standards.join(" · ")
      : "";
    $("#form-error").classList.add("d-none");
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    renderForm(info, prefill);
    setView("calculator");

    if (preset && preset.result) {
      state.currentResult = {
        calculator_id: preset.calculator_id,
        calculator_name: preset.calculator_name,
        inputs: preset.inputs || {},
        result: preset.result,
        record_id: preset.id,
      };
      renderResult(preset.result);
      $("#result-empty").classList.add("d-none");
      $("#result-panel").classList.remove("d-none");
    } else {
      $("#result-panel").classList.add("d-none");
      $("#result-empty").classList.remove("d-none");
      if (state.chart) {
        state.chart.destroy();
        state.chart = null;
      }
    }
  }

  /* ------------------------------------------------------------------ 计算 */
  async function runCalculation() {
    if (!state.current) return;
    const errorBox = $("#form-error");
    errorBox.classList.add("d-none");

    let inputs;
    try {
      inputs = collectInputs();
    } catch (error) {
      showFormError(error.message);
      return;
    }

    const button = $("#btn-calc");
    const spinner = $("#calc-spinner");
    button.disabled = true;
    spinner.classList.remove("d-none");

    try {
      const data = await api("/api/calculators/" + state.current.id + "/calculate", {
        method: "POST",
        body: JSON.stringify({ inputs: inputs }),
      });
      state.currentResult = {
        calculator_id: data.calculator_id,
        calculator_name: data.calculator_name,
        inputs: data.inputs,
        result: data.result,
        record_id: data.record_id,
      };
      renderResult(data.result);
      applyQuota(data.quota);
      $("#result-empty").classList.add("d-none");
      $("#result-panel").classList.remove("d-none");
      toast("计算完成", "success");
    } catch (error) {
      showFormError(error.message);
    } finally {
      button.disabled = false;
      spinner.classList.add("d-none");
    }
  }

  function showFormError(message) {
    const box = $("#form-error");
    box.textContent = message;
    box.classList.remove("d-none");
  }

  /* -------------------------------------------------------------- 结果渲染 */
  function renderResult(result) {
    const headline = $("#result-headline");
    headline.innerHTML = (result.headline || []).map((item, index) => {
      const value = typeof item.value === "number" ? formatNumber(item.value) : esc(item.value);
      return (
        '<div class="col-12 col-sm-6 col-xl-4">' +
          '<div class="result-card' + (index === 0 ? " primary" : "") + '">' +
            '<div class="rc-label">' + esc(item.label) + "</div>" +
            '<div class="rc-value">' + value +
              (item.unit ? '<span class="rc-unit">' + esc(item.unit) + "</span>" : "") + "</div>" +
            (item.note ? '<div class="rc-note">' + esc(item.note) + "</div>" : "") +
          "</div>" +
        "</div>"
      );
    }).join("");

    $("#result-tables").innerHTML = (result.tables || []).map((section, index) => {
      const header = section.columns.map((column) => "<th>" + esc(column) + "</th>").join("");
      const body = section.rows.map((row) => {
        const cells = row.map((cell) => "<td>" + (typeof cell === "number" ? formatNumber(cell) : esc(cell)) + "</td>").join("");
        return "<tr>" + cells + "</tr>";
      }).join("");
      return (
        '<div class="result-section" ' + (index > 0 ? 'style="margin-top:0.9rem"' : "") + ">" +
          '<div class="rs-head"><i class="bi bi-table"></i>' + esc(section.title) + "</div>" +
          '<div class="table-responsive"><table class="table table-sm table-hover mb-0"><thead><tr>' + header +
            "</tr></thead><tbody>" + body + "</tbody></table></div>" +
          (section.note ? '<div class="rs-note">' + esc(section.note) + "</div>" : "") +
        "</div>"
      );
    }).join("");

    const notes = result.notes || [];
    const notesBox = $("#result-notes");
    if (notes.length) {
      notesBox.innerHTML = '<div class="fw-semibold mb-1"><i class="bi bi-info-circle me-1"></i>说明与假设</div><ul>' +
        notes.map((note) => "<li>" + esc(note) + "</li>").join("") + "</ul>";
      notesBox.classList.remove("d-none");
    } else {
      notesBox.classList.add("d-none");
    }

    renderChart(result.chart);
  }

  function renderChart(spec) {
    const wrap = $("#result-chart-wrap");
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    if (!spec || !window.Chart || !(spec.series || []).length) {
      wrap.classList.add("d-none");
      return;
    }
    wrap.classList.remove("d-none");
    $("#chart-title").textContent = spec.title || "";

    const isLog = spec.scale === "loglog";
    const datasets = spec.series.map((item, index) => ({
      label: item.name,
      data: (item.points || []).map((point) => ({ x: point[0], y: point[1] })),
      borderColor: CHART_COLORS[index % CHART_COLORS.length],
      backgroundColor: index === 0 ? "#0f2a47" : "transparent",
      pointRadius: index === 0 ? 5 : 0,
      pointHoverRadius: index === 0 ? 6 : 0,
      showLine: index !== 0,
      borderWidth: index === 0 ? 1 : 2,
      tension: 0.12,
    }));

    const axis = (label) => ({
      type: isLog ? "logarithmic" : "linear",
      title: { display: true, text: label, color: "#6b7d90", font: { size: 11 } },
      grid: { color: "#eef3f8" },
      ticks: {
        color: "#6b7d90",
        font: { size: 10 },
        callback: function (value) {
          return formatNumber(value);
        },
      },
    });

    const context = $("#result-chart").getContext("2d");
    state.chart = new Chart(context, {
      type: "scatter",
      data: { datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        scales: { x: axis(spec.x_label || "x"), y: axis(spec.y_label || "y") },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true, color: "#35506b" } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + "：" + formatNumber(ctx.parsed.x) + " → " + formatNumber(ctx.parsed.y);
              },
            },
          },
        },
      },
    });
  }

  /* ------------------------------------------------------------------ 导出 */
  async function exportCurrent(format) {
    if (!state.currentResult) {
      toast("请先完成一次计算再导出", "warning");
      return;
    }
    try {
      await downloadRequest("/api/export/calculation", {
        format: format,
        calculator_id: state.currentResult.calculator_id,
        calculator_name: state.currentResult.calculator_name,
        inputs: state.currentResult.inputs,
        result: state.currentResult.result,
      });
      toast("导出已开始（" + format.toUpperCase() + "）", "success");
    } catch (error) {
      toast(error.message, "danger");
    }
  }

  async function exportHistory(format) {
    if (!state.user) {
      toast("请先登录后再导出历史记录", "warning");
      return;
    }
    try {
      await downloadRequest("/api/history/export?format=" + encodeURIComponent(format));
      toast("历史记录导出已开始", "success");
    } catch (error) {
      toast(error.message, "danger");
    }
  }

  /* -------------------------------------------------------------- 认证与配额 */
  function applyQuota(quota) {
    state.quota = quota;
    if (!quota) return;
    const pill = $("#quota-pill");
    if (quota.unlimited) {
      $("#quota-text").textContent = "无限次";
      pill.classList.remove("is-empty");
    } else {
      $("#quota-text").textContent = "今日剩余 " + quota.remaining + "/" + quota.daily_limit;
      pill.classList.toggle("is-empty", quota.remaining <= 0);
    }
  }

  function renderAuthArea() {
    const area = $("#auth-area");
    if (state.user) {
      area.innerHTML =
        '<div class="dropdown">' +
          '<button class="btn btn-sm btn-light dropdown-toggle" type="button" data-bs-toggle="dropdown">' +
            '<i class="bi bi-person-circle me-1"></i>' + esc(state.user.username) + "</button>" +
          '<ul class="dropdown-menu dropdown-menu-end">' +
            '<li><span class="dropdown-item-text small text-muted">' + esc(state.user.email) + "</span></li>" +
            '<li><span class="dropdown-item-text small">' +
              (state.user.is_premium ? "专业版 · 无限次" : "免费版 · 每日限额") + "</span></li>" +
            '<li><hr class="dropdown-divider"></li>' +
            '<li><button class="dropdown-item" type="button" id="btn-logout">' +
              '<i class="bi bi-box-arrow-right me-2"></i>退出登录</button></li>' +
          "</ul>" +
        "</div>";
      $("#btn-logout").addEventListener("click", logout);
    } else {
      area.innerHTML = '<button class="btn btn-sm btn-light" id="btn-login" type="button">登录 / 注册</button>';
      $("#btn-login").addEventListener("click", () => openAuth("login"));
    }
  }

  async function refreshAuth() {
    try {
      const data = await api("/api/auth/me");
      state.user = data.user;
      applyQuota(data.quota);
    } catch (error) {
      state.user = null;
    }
    renderAuthArea();
  }

  function openAuth(mode) {
    state.authMode = mode;
    $("#auth-modal-title").textContent = mode === "login" ? "登录" : "注册";
    $("#auth-submit").textContent = mode === "login" ? "登录" : "注册并登录";
    $("#auth-username-group").classList.toggle("d-none", mode === "login");
    $("#auth-password-hint").textContent = mode === "login" ? "" : "至少 8 位字符";
    $("#auth-error").classList.add("d-none");
    $$("#auth-tabs .nav-link").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.authTab === mode);
    });
    bootstrap.Modal.getOrCreateInstance($("#authModal")).show();
  }

  async function submitAuth(event) {
    event.preventDefault();
    const email = $("#auth-email").value.trim();
    const password = $("#auth-password").value;
    const username = $("#auth-username").value.trim();
    const errorBox = $("#auth-error");
    errorBox.classList.add("d-none");

    if (!email || !password) {
      errorBox.textContent = "请填写邮箱与口令";
      errorBox.classList.remove("d-none");
      return;
    }
    if (state.authMode === "register" && password.length < 8) {
      errorBox.textContent = "口令至少 8 位";
      errorBox.classList.remove("d-none");
      return;
    }

    const submit = $("#auth-submit");
    submit.disabled = true;
    try {
      const body = state.authMode === "login"
        ? { email: email, password: password }
        : { email: email, username: username, password: password };
      const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      const data = await api(path, { method: "POST", body: JSON.stringify(body) });
      state.token = data.access_token;
      localStorage.setItem("semirel_token", state.token);
      state.user = data.user;
      applyQuota(data.quota);
      renderAuthArea();
      bootstrap.Modal.getOrCreateInstance($("#authModal")).hide();
      toast(state.authMode === "login" ? "已登录" : "注册成功，已自动登录", "success");
      if (state.view === "history") loadHistory();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    } finally {
      submit.disabled = false;
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (error) {
      /* 忽略退出接口异常 */
    }
    state.token = null;
    state.user = null;
    localStorage.removeItem("semirel_token");
    renderAuthArea();
    await refreshAuth();
    toast("已退出登录", "secondary");
    if (state.view === "history") loadHistory();
  }

  /* -------------------------------------------------------------- 历史记录 */
  function readTime(record) {
    const raw = record.created_at;
    if (!raw) return "—";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return esc(raw);
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function renderHistory(records) {
    const host = $("#history-body");
    if (!records.length) {
      host.innerHTML =
        '<div class="empty-state"><i class="bi bi-inbox"></i><h5>暂无记录</h5>' +
        "<p>完成一次计算后，记录会自动出现在这里。</p></div>";
      return;
    }
    const rows = records.map((record) => {
      return (
        "<tr>" +
          '<td class="text-nowrap small text-muted">' + readTime(record) + "</td>" +
          "<td><span class=\"badge badge-lite\">" + esc(record.calculator_name) + "</span></td>" +
          '<td class="history-summary">' + esc(record.summary || "—") + "</td>" +
          '<td class="text-end text-nowrap">' +
            '<button class="btn btn-sm btn-outline-secondary me-1" data-record-view="' + record.id + '">查看</button>' +
            '<button class="btn btn-sm btn-outline-primary me-1" data-record-load="' + record.id + '">载入</button>' +
            '<button class="btn btn-sm btn-outline-danger" data-record-delete="' + record.id + '">删除</button>' +
          "</td>" +
        "</tr>"
      );
    }).join("");

    host.innerHTML =
      '<div class="table-responsive"><table class="table table-hover history-table mb-0">' +
        '<thead><tr><th>时间</th><th>计算器</th><th>主要结果</th><th class="text-end">操作</th></tr></thead>' +
        "<tbody>" + rows + "</tbody></table></div>";
  }

  let cachedRecords = [];

  async function loadHistory() {
    const host = $("#history-body");
    if (!state.user) {
      host.innerHTML =
        '<div class="empty-state"><i class="bi bi-person-lock"></i><h5>请先登录</h5>' +
        "<p>登录后，每次计算都会自动存档，并可批量导出。</p>" +
        '<button class="btn btn-primary btn-sm mt-2" id="history-login">登录 / 注册</button></div>';
      const loginButton = $("#history-login");
      if (loginButton) loginButton.addEventListener("click", () => openAuth("login"));
      return;
    }
    host.innerHTML = '<div class="p-4 text-center"><div class="spinner-border text-primary"></div></div>';
    try {
      const data = await api("/api/history?limit=50");
      cachedRecords = data.records || [];
      renderHistory(cachedRecords);
    } catch (error) {
      host.innerHTML = '<div class="alert alert-danger m-3 mb-3">' + esc(error.message) + "</div>";
    }
  }

  async function handleRecordAction(event) {
    const viewButton = event.target.closest("[data-record-view]");
    const loadButton = event.target.closest("[data-record-load]");
    const deleteButton = event.target.closest("[data-record-delete]");

    if (viewButton) {
      showRecord(Number(viewButton.dataset.recordView));
      return;
    }
    if (loadButton) {
      const record = cachedRecords.find((item) => item.id === Number(loadButton.dataset.recordLoad));
      if (record) openCalculator(record.calculator_id, record.inputs, record);
      return;
    }
    if (deleteButton) {
      const id = Number(deleteButton.dataset.recordDelete);
      if (!window.confirm("确定删除这条记录？删除后不可恢复。")) return;
      try {
        await api("/api/history/" + id, { method: "DELETE" });
        toast("记录已删除", "success");
        loadHistory();
      } catch (error) {
        toast(error.message, "danger");
      }
    }
  }

  async function showRecord(id) {
    const record = cachedRecords.find((item) => item.id === id);
    if (!record) return;
    state.recordToLoad = record;
    $("#record-title").textContent = record.calculator_name + " · " + readTime(record);
    const inputs = Object.keys(record.inputs || {}).map((key) => {
      const value = record.inputs[key];
      return "<li><span class=\"text-muted\">" + esc(key) + "：</span>" + esc(value) + "</li>";
    }).join("");
    $("#record-body").innerHTML =
      (inputs ? '<div class="mb-3"><h6 class="fw-semibold">输入参数</h6><ul class="small mb-0 ps-3">' + inputs + "</ul></div>" : "") +
      '<div class="row g-3">' +
        (record.result.headline || []).map((item) => (
          '<div class="col-6 col-md-4"><div class="result-card">' +
            '<div class="rc-label">' + esc(item.label) + "</div>" +
            '<div class="rc-value">' + (typeof item.value === "number" ? formatNumber(item.value) : esc(item.value)) +
              (item.unit ? '<span class="rc-unit">' + esc(item.unit) + "</span>" : "") + "</div>" +
          "</div></div>"
        )).join("") +
      "</div>" +
      (record.result.tables || []).map((section) => (
        '<div class="result-section mt-3"><div class="rs-head">' + esc(section.title) + "</div>" +
        '<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr>' +
          section.columns.map((column) => "<th>" + esc(column) + "</th>").join("") +
        "</tr></thead><tbody>" +
          section.rows.map((row) => "<tr>" + row.map((cell) => "<td>" +
            (typeof cell === "number" ? formatNumber(cell) : esc(cell)) + "</td>").join("") + "</tr>").join("") +
        "</tbody></table></div></div>"
      )).join("");
    bootstrap.Modal.getOrCreateInstance($("#recordModal")).show();
  }

  /* ------------------------------------------------------------------ 初始化 */
  function bindEvents() {
    $$("[data-view]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.preventDefault();
        setView(element.dataset.view);
      });
    });

    $("#btn-calc").addEventListener("click", runCalculation);
    $("#calc-form").addEventListener("submit", (event) => {
      event.preventDefault();
      runCalculation();
    });

    $("#btn-example").addEventListener("click", async () => {
      if (!state.current) return;
      try {
        const data = await api("/api/calculators/" + state.current.id + "/example");
        fillForm(data.inputs || {});
        toast("已载入示例参数", "success");
      } catch (error) {
        toast(error.message, "danger");
      }
    });

    $("#btn-clear").addEventListener("click", () => {
      if (!state.current) return;
      const defaults = {};
      state.current.input_fields.forEach((field) => {
        if (field.default !== null && field.default !== undefined) defaults[field.name] = field.default;
      });
      renderForm(state.current, defaults);
      $("#form-error").classList.add("d-none");
      $("#result-panel").classList.add("d-none");
      $("#result-empty").classList.remove("d-none");
      state.currentResult = null;
    });

    $$("[data-export]").forEach((button) => {
      button.addEventListener("click", () => exportCurrent(button.dataset.export));
    });

    $$("[data-history-export]").forEach((button) => {
      button.addEventListener("click", () => exportHistory(button.dataset.historyExport));
    });

    $("#btn-history-refresh").addEventListener("click", loadHistory);
    $("#history-body").addEventListener("click", handleRecordAction);

    $$("#auth-tabs .nav-link").forEach((tab) => {
      tab.addEventListener("click", () => openAuth(tab.dataset.authTab));
    });
    $("#auth-form").addEventListener("submit", submitAuth);

    $("#btn-record-load").addEventListener("click", () => {
      const record = state.recordToLoad;
      if (record) {
        bootstrap.Modal.getOrCreateInstance($("#recordModal")).hide();
        openCalculator(record.calculator_id, record.inputs, record);
      }
    });
  }

  async function boot() {
    bindEvents();
    renderAuthArea();
    await Promise.all([refreshAuth(), loadCalculators()]);
  }

  async function loadCalculators() {
    try {
      const data = await api("/api/calculators");
      state.calculators = data.calculators || [];
      renderCalculatorGrid();
    } catch (error) {
      $("#calculator-grid").innerHTML =
        '<div class="col-12"><div class="alert alert-danger mb-0">无法加载计算器：' + esc(error.message) + "</div></div>";
    }
  }

  /* 历史记录缓存：每次加载后供查看/载入使用 */
  boot();
})();
