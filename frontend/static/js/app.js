const API_BASE = "/api/v1";
const fileInput = document.getElementById("fileInput");
const documentType = document.getElementById("documentType");
const processButton = document.getElementById("processButton");

const uploadError = document.getElementById("uploadError");
const resultSection = document.getElementById("resultSection");

const apiStatus = document.getElementById("apiStatus");

const fieldsContainer = document.getElementById("fieldsContainer");
const tablesContainer = document.getElementById("tablesContainer");

const lineItemsSection = document.getElementById("lineItemsSection");
const lineItemsBody = document.getElementById("lineItemsBody");

const validationBody = document.getElementById("validationBody");
const validationIssues = document.getElementById("validationIssues");

const extractionIssuesSection =
    document.getElementById("extractionIssuesSection");

const extractionIssues =
    document.getElementById("extractionIssues");

const historyBody = document.getElementById("historyBody");

const rawJson = document.getElementById("rawJson");
const toggleJsonButton =
    document.getElementById("toggleJsonButton");

const refreshHistoryButton =
    document.getElementById("refreshHistoryButton");


function escapeHtml(value) {
    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function setStatus(element, status) {
    element.className = "status-badge";

    if (status === "PASS") {
        element.classList.add("status-pass");
    } else if (status === "FAILED" || status === "FAIL") {
        element.classList.add("status-fail");
    } else {
        element.classList.add("status-na");
    }

    element.textContent = status || "N/A";
}


async function checkApiHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);

        if (!response.ok) {
            throw new Error("API unavailable");
        }

        apiStatus.textContent = "API Connected";
        apiStatus.className = "status-badge status-pass";

    } catch (error) {
        apiStatus.textContent = "API Offline";
        apiStatus.className = "status-badge status-fail";
    }
}


function renderFields(fields) {
    fieldsContainer.innerHTML = "";

    if (!fields || fields.length === 0) {
        fieldsContainer.innerHTML =
            "<p>No fields extracted.</p>";
        return;
    }

    fields.forEach(field => {

        const value =
            field.value === null ||
            field.value === undefined ||
            field.value === ""
                ? "Missing"
                : field.value;

        const missing =
            field.value === null ||
            field.value === undefined ||
            field.value === "";

        const div = document.createElement("div");

        div.className = `field ${missing ? "missing" : ""}`;

        div.innerHTML = `
            <span class="field-name">
                ${escapeHtml(field.name)}
            </span>

            <span class="field-value">
                ${escapeHtml(value)}
            </span>

            ${
                field.evidence
                    ? `<small>
                        Evidence: ${escapeHtml(field.evidence)}
                       </small>`
                    : ""
            }

            ${
                field.page_number
                    ? `<small>
                        Page: ${escapeHtml(field.page_number)}
                       </small>`
                    : ""
            }
        `;

        fieldsContainer.appendChild(div);
    });
}


function renderLineItems(items) {
    lineItemsBody.innerHTML = "";

    if (!items || items.length === 0) {
        lineItemsSection.classList.add("hidden");
        return;
    }

    lineItemsSection.classList.remove("hidden");

    items.forEach(item => {

        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${escapeHtml(item.description ?? "Missing")}</td>
            <td>${escapeHtml(item.quantity ?? "Missing")}</td>
            <td>${escapeHtml(item.unit_price ?? "Missing")}</td>
            <td>${escapeHtml(item.amount ?? "Missing")}</td>
            <td>${escapeHtml(item.tax_rate ?? "Missing")}</td>
        `;

        lineItemsBody.appendChild(row);
    });
}


function renderTables(tables) {
    tablesContainer.innerHTML = "";

    if (!tables || tables.length === 0) {
        tablesContainer.innerHTML =
            "<p>No tables extracted.</p>";
        return;
    }

    tables.forEach(table => {

        const wrapper = document.createElement("div");

        wrapper.style.marginBottom = "30px";

        let html = `
            <h3>${escapeHtml(table.name)}</h3>
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
        `;

        if (table.columns && table.columns.length > 0) {
            table.columns.forEach(column => {
                html += `<th>${escapeHtml(column)}</th>`;
            });
        } else {
            html += "<th>Row</th>";
        }

        html += `
                    </tr>
                </thead>
                <tbody>
        `;

        (table.rows || []).forEach(row => {

            html += "<tr>";

            if (table.columns && table.columns.length > 0) {

                html += `
                    <td>
                        ${escapeHtml(row.label ?? "")}
                    </td>
                `;

                const values = row.values || [];

                for (let i = 1; i < table.columns.length; i++) {

                    const value = values[i - 1];

                    html += `
                        <td>
                            ${escapeHtml(value?.value ?? "Missing")}
                        </td>
                    `;
                }

            } else {

                html += `
                    <td>
                        ${escapeHtml(row.label ?? "Missing")}
                    </td>
                `;

            }

            html += "</tr>";
        });

        html += `
                </tbody>
            </table>
            </div>
        `;

        wrapper.innerHTML = html;

        tablesContainer.appendChild(wrapper);
    });
}


function renderValidation(validation) {
    validationBody.innerHTML = "";
    validationIssues.innerHTML = "";

    if (!validation) {
        validationBody.innerHTML =
            "<tr><td colspan='6'>No validation data.</td></tr>";
        return;
    }

    setStatus(
        document.getElementById("validationStatus"),
        validation.overall_status
    );

    (validation.issues || []).forEach(issue => {

        const div = document.createElement("div");

        div.className = "issue";
        div.textContent = issue;

        validationIssues.appendChild(div);
    });

    const checks = validation.checks || [];

    if (checks.length === 0) {
        validationBody.innerHTML = `
            <tr>
                <td colspan="6">
                    No financial validation checks applicable.
                </td>
            </tr>
        `;
        return;
    }

    checks.forEach(check => {

        const status = check.status || "NOT_APPLICABLE";

        let statusClass = "validation-na";

        if (status === "PASS") {
            statusClass = "validation-pass";
        } else if (status === "FAIL") {
            statusClass = "validation-fail";
        }

        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${escapeHtml(check.name ?? check.check ?? "-")}</td>
            <td>${escapeHtml(check.formula ?? "-")}</td>
            <td>${escapeHtml(check.calculated_value ?? "-")}</td>
            <td>${escapeHtml(check.reported_value ?? "-")}</td>
            <td>${escapeHtml(check.variance ?? "-")}</td>
            <td class="${statusClass}">
                ${escapeHtml(status)}
            </td>
        `;

        validationBody.appendChild(row);
    });
}


function renderExtractionIssues(issues) {

    extractionIssues.innerHTML = "";

    if (!issues || issues.length === 0) {
        extractionIssuesSection.classList.add("hidden");
        return;
    }

    extractionIssuesSection.classList.remove("hidden");

    issues.forEach(issue => {

        const li = document.createElement("li");

        li.textContent = issue;

        extractionIssues.appendChild(li);
    });
}


function renderResult(result) {

    resultSection.classList.remove("hidden");

    document.getElementById("resultDocumentName").textContent =
        result.document_name || "Document";

    document.getElementById("resultDocumentType").textContent =
        result.document_type || "-";

    setStatus(
        document.getElementById("processingStatus"),
        result.processing_status
    );

    const fileValidation = result.file_validation || {};
    const metadata = result.processing_metadata || {};

    document.getElementById("fileType").textContent =
        fileValidation.file_type || "-";

    document.getElementById("pageCount").textContent =
        fileValidation.page_count ?? "-";

    document.getElementById("ocrUsed").textContent =
        metadata.ocr_used ? "Yes" : "No";

    document.getElementById("processingTime").textContent =
        metadata.processing_time_ms !== undefined
            ? `${metadata.processing_time_ms} ms`
            : "-";

    const extractedData = result.extracted_data || {};

    renderFields(extractedData.fields || []);
    renderLineItems(extractedData.line_items || []);
    renderTables(extractedData.tables || []);

    renderValidation(result.validation);
    renderExtractionIssues(result.extraction_issues);

    rawJson.textContent =
        JSON.stringify(result, null, 2);
}


async function processDocument() {

    uploadError.classList.add("hidden");
    uploadError.textContent = "";

    const file = fileInput.files[0];

    if (!file) {
        uploadError.textContent =
            "Please select a document first.";

        uploadError.classList.remove("hidden");

        return;
    }

    processButton.disabled = true;
    processButton.textContent = "Processing...";

    const formData = new FormData();

    formData.append("file", file);
    formData.append(
        "document_type",
        documentType.value
    );

    try {

        const response = await fetch(
            `${API_BASE}/documents/process`,
            {
                method: "POST",
                body: formData
            }
        );

        const data = await response.json();

        if (!response.ok) {
            const message =
                data?.detail?.error?.message ||
                data?.detail?.message ||
                data?.detail ||
                data?.message ||
                "Document processing failed.";

            throw new Error(
                typeof message === "string"
                    ? message
                    : "Document processing failed."
            );
        }

        renderResult(data);

        await loadHistory();

    } catch (error) {

        uploadError.textContent =
            error.message || "Something went wrong.";

        uploadError.classList.remove("hidden");

    } finally {

        processButton.disabled = false;
        processButton.textContent = "Process Document";
    }
}


async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/documents`);

        if (!response.ok) {
            throw new Error(`History API returned ${response.status}`);
        }

        const data = await response.json();

        historyBody.innerHTML = "";

        const documents = data.documents || [];

        if (documents.length === 0) {
            historyBody.innerHTML = `
                <tr>
                    <td colspan="5">
                        No processed documents yet.
                    </td>
                </tr>
            `;
            return;
        }

        documents.forEach(item => {
            const row = window.document.createElement("tr");

            row.style.cursor = "pointer";

            const statusClass =
                item.processing_status === "PASS"
                    ? "status-pass"
                    : "status-fail";

            const processedTime = item.processed_at
                ? new Date(item.processed_at).toLocaleString()
                : "-";

            row.innerHTML = `
                <td>${escapeHtml(item.document_name || "-")}</td>

                <td>${escapeHtml(item.document_type || "-")}</td>

                <td>
                    <span class="status-badge ${statusClass}">
                        ${escapeHtml(item.processing_status || "-")}
                    </span>
                </td>

                <td>${escapeHtml(item.page_count ?? "-")}</td>

                <td>${escapeHtml(processedTime)}</td>
            `;

            row.addEventListener("click", () => {
                loadSavedDocument(item.document_name);
            });

            historyBody.appendChild(row);
        });

    } catch (error) {
        console.error("History loading error:", error);

        historyBody.innerHTML = `
            <tr>
                <td colspan="5">
                    Could not load processing history.
                </td>
            </tr>
        `;
    }
}

async function loadSavedDocument(documentName) {
    try {
        const response = await fetch(
            `${API_BASE}/documents/${encodeURIComponent(documentName)}`
        );

        if (!response.ok) {
            throw new Error("Could not retrieve saved document.");
        }

        const result = await response.json();

        renderResult(result);

        resultSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    } catch (error) {
        uploadError.textContent =
            error.message || "Could not load saved document.";

        uploadError.classList.remove("hidden");
    }
}

toggleJsonButton.addEventListener(
    "click",
    () => {

        const hidden =
            rawJson.classList.toggle("hidden");

        toggleJsonButton.textContent =
            hidden
                ? "Show JSON"
                : "Hide JSON";
    }
);


processButton.addEventListener(
    "click",
    processDocument
);


refreshHistoryButton.addEventListener(
    "click",
    loadHistory
);


checkApiHealth();
loadHistory();