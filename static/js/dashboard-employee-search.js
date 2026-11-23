(() => {
    const normalize = (value) => value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/g, "d")
        .replace(/Đ/g, "D")
        .toLocaleLowerCase("vi")
        .trim();

    const attachSearch = ({ formSelector, inputSelector, countSelector, sectionSelector, rowSelector, dataKey, entityName }) => {
        const form = document.querySelector(formSelector);
        if (!form) return;

        const input = form.querySelector(inputSelector);
        const count = form.querySelector(countSelector);
        const table = document.querySelector(`${sectionSelector} .dashboard-table`);
        const body = table?.tBodies[0];
        if (!input || !count || !body) return;

        const rows = Array.from(body.querySelectorAll(rowSelector));
        const noResults = document.createElement("tr");
        noResults.hidden = true;
        noResults.innerHTML = `<td class="table-empty" colspan="${table.tHead.rows[0].cells.length}">Không tìm thấy ${entityName} phù hợp.</td>`;
        body.append(noResults);

        const filterRows = () => {
            const query = normalize(input.value);
            let visibleCount = 0;
            rows.forEach((row) => {
                const matches = !query || normalize(row.dataset[dataKey] || "").includes(query);
                row.hidden = !matches;
                if (matches) visibleCount += 1;
            });
            noResults.hidden = visibleCount > 0 || rows.length === 0;
            count.textContent = query
                ? `Tìm thấy ${visibleCount}/${rows.length} ${entityName}`
                : `${rows.length} ${entityName}`;
        };

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            filterRows();
        });
        input.addEventListener("input", filterRows);
    };

    attachSearch({
        formSelector: "[data-employee-search-form]",
        inputSelector: "[data-employee-search-input]",
        countSelector: "[data-employee-search-count]",
        sectionSelector: "#employees-section",
        rowSelector: "[data-employee-search-row]",
        dataKey: "employeeSearch",
        entityName: "nhân viên",
    });
    attachSearch({
        formSelector: "[data-customer-search-form]",
        inputSelector: "[data-customer-search-input]",
        countSelector: "[data-customer-search-count]",
        sectionSelector: "#customers-section",
        rowSelector: "[data-customer-search-row]",
        dataKey: "customerSearch",
        entityName: "khách hàng",
    });
    attachSearch({
        formSelector: "[data-product-search-form]",
        inputSelector: "[data-product-search-input]",
        countSelector: "[data-product-search-count]",
        sectionSelector: "#products-section",
        rowSelector: "[data-product-search-row]",
        dataKey: "productSearch",
        entityName: "sản phẩm",
    });
})();
