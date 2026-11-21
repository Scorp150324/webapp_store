"use strict";

const dashboardViews = Array.from(
    document.querySelectorAll("[data-dashboard-view]"),
);
const dashboardLinks = Array.from(
    document.querySelectorAll(".dashboard-menu a[href^='#']"),
);
const legacyViewNames = {
    "employee-section": "employees",
    "customer-section": "customers",
    "product-section": "products",
    "inventory-section": "inbound",
};
let analyticsRequestKey = "";

function updateAnalytics(data) {
    const formatMoney = new Intl.NumberFormat("vi-VN", {
        maximumFractionDigits: 0,
    });
    document.getElementById("analytics-period-label").textContent = data.period;
    document.getElementById("analytics-sales-total").textContent =
        `${formatMoney.format(data.period_sales)} ₫`;
    document.getElementById("analytics-order-count").textContent =
        formatMoney.format(data.period_order_count);

    const chartPeriod = document.getElementById("analytics-chart-period");
    const period = document.querySelector('[data-analytics-form] select[name="period"]').value;
    chartPeriod.textContent = period === "day"
        ? "Theo giờ"
        : period === "month"
          ? "Theo ngày trong tháng"
          : "Theo tháng trong năm";

    window.renderDashboardCharts?.(data);
    document.querySelectorAll("[data-analytics-export]").forEach((link) => {
        const format = link.dataset.analyticsExport;
        link.href = `/dashboard/statistics/${format}?period=${encodeURIComponent(data.period_type)}&date=${encodeURIComponent(data.selected_date)}`;
    });
}

async function loadAnalytics(force = false) {
    const form = document.querySelector("[data-analytics-form]");
    const loading = document.getElementById("analytics-loading");
    if (!form || !loading) return;

    const values = new FormData(form);
    const period = values.get("period");
    const date = values.get("date");
    const key = `${period}:${date}`;
    if (!force && analyticsRequestKey === key) return;

    analyticsRequestKey = key;
    loading.textContent = "Đang tải thống kê…";
    loading.hidden = false;
    try {
        const params = new URLSearchParams({ period, date });
        const response = await fetch(`/dashboard/analytics?${params}`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error("Không thể tải thống kê.");
        const data = await response.json();
        if (analyticsRequestKey !== key) return;
        data.period_type = period;
        updateAnalytics(data);
        loading.hidden = true;
    } catch (error) {
        analyticsRequestKey = "";
        loading.textContent = "Không thể tải thống kê. Vui lòng thử lại.";
    }
}

function viewNameFromHash() {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (!hash) return "overview";
    if (legacyViewNames[hash]) return legacyViewNames[hash];

    const target = document.getElementById(hash);
    return target?.dataset.dashboardView || "overview";
}

function showDashboardView() {
    const selectedView = viewNameFromHash();
    const matchingView = dashboardViews.find(
        (view) => view.dataset.dashboardView === selectedView,
    );
    const activeView = matchingView?.dataset.dashboardView || "overview";

    dashboardViews.forEach((view) => {
        view.hidden = view.dataset.dashboardView !== activeView;
    });
    dashboardLinks.forEach((link) => {
        const target = document.getElementById(
            decodeURIComponent(link.hash.slice(1)),
        );
        const isActive = target?.dataset.dashboardView === activeView;
        if (isActive) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });
    if (activeView === "analytics") loadAnalytics();
}

const inboundProduct = document.querySelector("[data-inbound-product]");
const inboundCostInput = document.querySelector("[data-inbound-cost-input]");
const updateInboundCost = () => {
    const cost = Number(inboundProduct?.selectedOptions[0]?.dataset.costPrice);
    if (inboundCostInput && Number.isFinite(cost)) inboundCostInput.value = String(Math.round(cost));
};
inboundProduct?.addEventListener("change", updateInboundCost);
updateInboundCost();

document.querySelector("[data-analytics-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    loadAnalytics(true);
});

window.addEventListener("hashchange", showDashboardView);
showDashboardView();
