"use strict";

const chartColors = [
    "#2563eb",
    "#14b8a6",
    "#f97316",
    "#8b5cf6",
    "#e11d48",
    "#84cc16",
    "#0891b2",
    "#d946ef",
    "#64748b",
];

function readChartData(id) {
    const element = document.getElementById(id);
    if (!element) return null;
    try {
        return JSON.parse(element.textContent);
    } catch (error) {
        console.error(`Invalid chart data in ${id}`, error);
        return null;
    }
}

function svgElement(name, attributes = {}) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) {
        element.setAttribute(key, String(value));
    }
    return element;
}

function renderRevenueChart(data) {
    const svg = document.getElementById("revenue-line-chart");
    if (!svg || !data || !Array.isArray(data.labels) || !Array.isArray(data.values)) return;

    const width = 720;
    const height = 280;
    const margin = { top: 16, right: 16, bottom: 36, left: 66 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const maxValue = Math.max(1, ...data.values);
    const pointX = (index) =>
        margin.left + (data.values.length < 2 ? plotWidth / 2 : (index * plotWidth) / (data.values.length - 1));
    const pointY = (value) => margin.top + plotHeight - (value / maxValue) * plotHeight;

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.replaceChildren();

    for (let index = 0; index <= 4; index += 1) {
        const value = (maxValue * index) / 4;
        const y = pointY(value);
        svg.append(
            svgElement("line", {
                x1: margin.left,
                x2: width - margin.right,
                y1: y,
                y2: y,
                class: "chart-grid-line",
            }),
        );
        const label = svgElement("text", {
            x: margin.left - 8,
            y: y + 3,
            "text-anchor": "end",
            class: "chart-axis-label",
        });
        label.textContent = new Intl.NumberFormat("vi-VN", {
            notation: "compact",
            maximumFractionDigits: 1,
        }).format(value);
        svg.append(label);
    }

    const points = data.values.map((value, index) => [pointX(index), pointY(value)]);
    if (points.length > 0) {
        const linePoints = points.map(([x, y]) => `${x},${y}`).join(" ");
        const areaPoints = `${margin.left},${margin.top + plotHeight} ${linePoints} ${width - margin.right},${margin.top + plotHeight}`;
        svg.append(svgElement("polygon", { points: areaPoints, class: "chart-revenue-area" }));
        svg.append(svgElement("polyline", { points: linePoints, class: "chart-revenue-line" }));
        points.forEach(([x, y], index) => {
            const point = svgElement("circle", {
                cx: x,
                cy: y,
                r: 3.5,
                class: "chart-revenue-point",
            });
            const title = svgElement("title");
            title.textContent = `${data.labels[index]}: ${new Intl.NumberFormat("vi-VN").format(data.values[index])} ₫`;
            point.append(title);
            svg.append(point);
        });
    }

    const labelStep = Math.max(1, Math.ceil(data.labels.length / 7));
    data.labels.forEach((value, index) => {
        if (index % labelStep !== 0 && index !== data.labels.length - 1) return;
        const label = svgElement("text", {
            x: pointX(index),
            y: height - 10,
            "text-anchor": "middle",
            class: "chart-axis-label",
        });
        label.textContent = value;
        svg.append(label);
    });
}

function renderCategoryChart(data) {
    const svg = document.getElementById("category-pie-chart");
    const legend = document.getElementById("category-chart-legend");
    if (!svg || !legend || !Array.isArray(data)) return;

    const width = 240;
    const center = width / 2;
    const radius = 96;
    const total = data.reduce((sum, item) => sum + item.value, 0);
    svg.setAttribute("viewBox", `0 0 ${width} ${width}`);
    svg.replaceChildren();
    legend.replaceChildren();

    if (total <= 0) {
        const emptyCircle = svgElement("circle", {
            cx: center,
            cy: center,
            r: radius,
            fill: "#e2e8f0",
        });
        const emptyLabel = svgElement("text", {
            x: center,
            y: center + 4,
            class: "chart-empty-label",
        });
        emptyLabel.textContent = "Chưa có dữ liệu";
        svg.append(emptyCircle, emptyLabel);
        return;
    }

    let angle = -Math.PI / 2;
    data.forEach((item, index) => {
        const color = chartColors[index % chartColors.length];
        const sliceAngle = (item.value / total) * Math.PI * 2;
        const endAngle = angle + sliceAngle;
        const x1 = center + radius * Math.cos(angle);
        const y1 = center + radius * Math.sin(angle);
        const x2 = center + radius * Math.cos(endAngle);
        const y2 = center + radius * Math.sin(endAngle);

        let slice;
        if (sliceAngle >= Math.PI * 2 - 0.000001) {
            slice = svgElement("circle", {
                cx: center,
                cy: center,
                r: radius,
                fill: color,
                class: "chart-pie-slice",
            });
        } else {
            const largeArc = sliceAngle > Math.PI ? 1 : 0;
            const path = [
                `M ${center} ${center}`,
                `L ${x1} ${y1}`,
                `A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`,
                "Z",
            ].join(" ");
            slice = svgElement("path", { d: path, fill: color, class: "chart-pie-slice" });
        }
        const title = svgElement("title");
        title.textContent = `${item.label}: ${new Intl.NumberFormat("vi-VN").format(item.value)} ₫`;
        slice.append(title);
        svg.append(slice);
        angle = endAngle;

        const entry = document.createElement("li");
        const swatch = document.createElement("span");
        swatch.className = "chart-legend-swatch";
        swatch.style.backgroundColor = color;
        const label = document.createElement("span");
        label.textContent = item.label;
        const amount = document.createElement("strong");
        amount.textContent = `${new Intl.NumberFormat("vi-VN").format(item.value)} ₫`;
        label.append(amount);
        entry.append(swatch, label);
        legend.append(entry);
    });
}

renderRevenueChart(readChartData("revenue-chart-data"));
renderCategoryChart(readChartData("category-chart-data"));
