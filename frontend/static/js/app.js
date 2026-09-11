const API_BASE = "/api/v1";

const fileInput = document.getElementById("fileInput");
const documentType = document.getElementById("documentType");
const processButton = document.getElementById("processButton");

const selectedFileName = document.getElementById("selectedFileName");
const selectedFileType = document.getElementById("selectedFileType");

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


// ---------------------------------------------------------
// HELPERS
// ---------------------------------------------------------

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


function isMissing(value) {
    return (
        value === null ||
        value === undefined ||
        String(value).trim() === "" ||
        String(value).trim().toLowerCase() === "missing"
    );
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


// ---------------------------------------------------------
// API HEALTH
// ---------------------------------------------------------

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


// ---------------------------------------------------------
// RENDER FIELDS
// ---------------------------------------------------------

function renderFields(fields) {
    fieldsContainer.innerHTML = "";

    const visibleFields = (fields || []).filter(
        field => !isMissing(field.value)
    );

    if (visibleFields.length === 0) {
        fieldsContainer.innerHTML =
            "<p>No fields extracted.</p>";
        return;
    }

    visibleFields.forEach(field => {
        const div = document.createElement("div");

        div.className = "field";

        div.innerHTML = `
            <span class="field-name">
                ${escapeHtml(field.name)}
            </span>

            <span class="field-value">
                ${escapeHtml(field.value)}
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


// ---------------------------------------------------------
// RENDER LINE ITEMS
// ---------------------------------------------------------

function renderLineItems(items) {
    lineItemsBody.innerHTML = "";

    const visibleItems = (items || []).filter(item => {
        return [
            item.description,
            item.quantity,
            item.unit_price,
            item.amount,
            item.tax_rate
        ].some(value => !isMissing(value));
    });

    if (visibleItems.length === 0) {
        lineItemsSection.classList.add("hidden");
        return;
    }

    lineItemsSection.classList.remove("hidden");

    visibleItems.forEach(item => {
        const row = document.createElement("tr");

        const description = isMissing(item.description)
            ? ""
            : item.description;

        const quantity = isMissing(item.quantity)
            ? ""
            : item.quantity;

        const unitPrice = isMissing(item.unit_price)
            ? ""
            : item.unit_price;

        const amount = isMissing(item.amount)
            ? ""
            : item.amount;

        const taxRate = isMissing(item.tax_rate)
            ? ""
            : item.tax_rate;

        row.innerHTML = `
            <td>${escapeHtml(description)}</td>
            <td>${escapeHtml(quantity)}</td>
            <td>${escapeHtml(unitPrice)}</td>
            <td>${escapeHtml(amount)}</td>
            <td>${escapeHtml(taxRate)}</td>
        `;

        lineItemsBody.appendChild(row);
    });
}


// ---------------------------------------------------------
// RENDER TABLES
// ---------------------------------------------------------

function renderTables(tables, currentDocumentType) {
    tablesContainer.innerHTML = "";

    if (!tables || tables.length === 0) {
        tablesContainer.innerHTML =
            "<p>No tables extracted.</p>";
        return;
    }

    const documentType = String(currentDocumentType || "")
        .trim()
        .toLowerCase();


    // ------------------------------------------------------------
    // INVOICE
    // Invoice tables use:
    // columns: ["No.", "Description", "Qty", ...]
    // rows:    [["1", "Product", "5", ...], ...]
    // ------------------------------------------------------------

    if (documentType === "invoice") {
        tables.forEach(table => {
            const wrapper = document.createElement("div");

            wrapper.style.marginBottom = "30px";

            const columns = table.columns || [];
            const rows = table.rows || [];

            let html = `
                <h3>${escapeHtml(table.name || "Table")}</h3>

                <div class="table-wrapper">

                <table>

                    <thead>
                        <tr>
            `;

            // Table headers
            columns.forEach(column => {
                html += `
                    <th>
                        ${escapeHtml(column)}
                    </th>
                `;
            });

            html += `
                        </tr>
                    </thead>

                    <tbody>
            `;

            // Table rows
            rows.forEach(row => {
                html += "<tr>";

                columns.forEach((column, columnIndex) => {

                    const value =
                        Array.isArray(row)
                            ? row[columnIndex]
                            : null;

                    html += `
                        <td>
                            ${
                                isMissing(value)
                                    ? ""
                                    : escapeHtml(value)
                            }
                        </td>
                    `;
                });

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

        return;
    }


    // ------------------------------------------------------------
    // FINANCIAL STATEMENTS
    // Balance Sheet
    // Profit & Loss
    // Cash Flow
    //
    // These are NOT generic tables.
    // We explicitly create the structure:
    //
    // Balance Sheet / P&L:
    // Particulars | Schedule | Period 1 | Period 2
    //
    // Cash Flow:
    // Particulars | Period 1 | Period 2
    // ------------------------------------------------------------

    const isStatement =
        documentType === "balance_sheet" ||
        documentType === "profit_and_loss" ||
        documentType === "cash_flow_statement";

    if (!isStatement) {
        return;
    }


    tables.forEach(table => {

        const wrapper = document.createElement("div");

        wrapper.style.marginBottom = "30px";

        const rows = table.rows || [];


        // --------------------------------------------------------
        // GET FINANCIAL PERIODS
        // --------------------------------------------------------

        let periods = [];

        rows.forEach(row => {

            (row.values || []).forEach(valueItem => {

                if (
                    valueItem &&
                    valueItem.period &&
                    !periods.includes(valueItem.period)
                ) {
                    periods.push(valueItem.period);
                }

            });

        });


        // Fallback to table columns if periods weren't found
        // in rows.

        if (periods.length === 0) {

            periods = (table.columns || []).filter(
                column =>
                    ![
                        "particulars",
                        "schedule",
                        "description"
                    ].includes(
                        String(column)
                            .trim()
                            .toLowerCase()
                    )
            );

        }


        // Balance Sheet and P&L have a Schedule column.

        const hasSchedule =
            documentType === "balance_sheet" ||
            documentType === "profit_and_loss";


        // --------------------------------------------------------
        // TABLE HEADER
        // --------------------------------------------------------

        let html = `
            <h3>
                ${escapeHtml(
                    table.name || "Financial Statement"
                )}
            </h3>

            <div class="table-wrapper">

            <table class="financial-statement-table">

                <thead>

                    <tr>

                        <th class="particulars-column">
                            Particulars
                        </th>
        `;


        if (hasSchedule) {

            html += `
                <th class="schedule-column">
                    Schedule
                </th>
            `;

        }


        periods.forEach(period => {

            html += `
                <th class="amount-column">
                    ${escapeHtml(period)}
                </th>
            `;

        });


        html += `
                    </tr>

                </thead>

                <tbody>
        `;


        // --------------------------------------------------------
        // TABLE ROWS
        // --------------------------------------------------------

        rows.forEach(row => {

            const rowType =
                String(row.type || "")
                    .trim()
                    .toLowerCase();


            const label =
                row.label ??
                row.schedule ??
                "";


            const isSectionHeader =
                rowType === "section_header" ||
                rowType === "section" ||
                rowType === "header";


            const isTotal =
                rowType === "total" ||
                String(label)
                    .trim()
                    .toLowerCase() === "total";


            const rowClass =
                isSectionHeader
                    ? "statement-section-row"
                    : isTotal
                        ? "statement-total-row"
                        : "statement-data-row";


            html += `
                <tr class="${rowClass}">
            `;


            // ----------------------------------------------------
            // PARTICULARS
            // ----------------------------------------------------

            html += `
                <td class="particulars-cell">
                    ${escapeHtml(label)}
                </td>
            `;


            // ----------------------------------------------------
            // SCHEDULE
            // ----------------------------------------------------

            if (hasSchedule) {

                const schedule =
                    row.schedule ??
                    row.schedule_number ??
                    "";

                html += `
                    <td class="schedule-cell">
                        ${escapeHtml(schedule)}
                    </td>
                `;

            }


            // ----------------------------------------------------
            // PERIOD VALUES
            // ----------------------------------------------------

            const rowValues = {};

            (row.values || []).forEach(valueItem => {

                if (
                    valueItem &&
                    valueItem.period
                ) {

                    rowValues[
                        String(valueItem.period)
                            .trim()
                            .toLowerCase()
                    ] = valueItem.value;

                }

            });


            periods.forEach(period => {

                const key =
                    String(period)
                        .trim()
                        .toLowerCase();


                const value =
                    rowValues[key];


                // Section headers don't have numerical values.
                // Leave them blank.

                if (isSectionHeader) {

                    html += `
                        <td class="amount-cell"></td>
                    `;

                    return;
                }


                // Missing values are displayed as blank.

                html += `
                    <td class="amount-cell">
                        ${
                            isMissing(value)
                                ? ""
                                : escapeHtml(value)
                        }
                    </td>
                `;

            });


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


// ---------------------------------------------------------
// RENDER VALIDATION
// ---------------------------------------------------------

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


    // Remove NOT_APPLICABLE checks completely.

    const visibleChecks = checks.filter(check => {

        const status =
            String(check.status || "")
                .trim()
                .toUpperCase();

        return status !== "NOT_APPLICABLE";

    });


    if (visibleChecks.length === 0) {

        validationBody.innerHTML = `
            <tr>
                <td colspan="6">
                    No financial validation checks applicable.
                </td>
            </tr>
        `;

        return;
    }


    visibleChecks.forEach(check => {

        const status = check.status || "";

        let statusClass = "validation-na";


        if (status === "PASS") {

            statusClass = "validation-pass";

        } else if (status === "FAIL") {

            statusClass = "validation-fail";

        }


        const row = document.createElement("tr");


        row.innerHTML = `
            <td>
                ${escapeHtml(
                    check.name ??
                    check.check ??
                    "-"
                )}
            </td>

            <td>
                ${escapeHtml(
                    check.formula ??
                    "-"
                )}
            </td>

            <td>
                ${escapeHtml(
                    check.calculated_value ??
                    "-"
                )}
            </td>

            <td>
                ${escapeHtml(
                    check.reported_value ??
                    "-"
                )}
            </td>

            <td>
                ${escapeHtml(
                    check.variance ??
                    "-"
                )}
            </td>

            <td class="${statusClass}">
                ${escapeHtml(status)}
            </td>
        `;


        validationBody.appendChild(row);

    });

}


// ---------------------------------------------------------
// EXTRACTION ISSUES
// ---------------------------------------------------------

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


// ---------------------------------------------------------
// RENDER COMPLETE RESULT
// ---------------------------------------------------------

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


    const fileValidation =
        result.file_validation || {};

    const metadata =
        result.processing_metadata || {};


    document.getElementById("fileType").textContent =
        fileValidation.file_type || "-";


    document.getElementById("pageCount").textContent =
        fileValidation.page_count ?? "-";


    document.getElementById("ocrUsed").textContent =
        metadata.ocr_used
            ? "Yes"
            : "No";


    document.getElementById("processingTime").textContent =
        metadata.processing_time_ms !== undefined
            ? `${metadata.processing_time_ms} ms`
            : "-";


    const extractedData =
        result.extracted_data || {};


    renderFields(
        extractedData.fields || []
    );


    const lineItems =
        extractedData.line_items || [];


    window.currentExtractedLineItems =
        lineItems;


    renderLineItems(
        extractedData.line_items || []
    );


    renderTables(
        extractedData.tables || [],
        result.document_type
    );


    renderValidation(
        result.validation
    );


    renderExtractionIssues(
        result.extraction_issues
    );


    // Raw JSON remains untouched.
    rawJson.textContent =
        JSON.stringify(
            result,
            null,
            2
        );
}


// ---------------------------------------------------------
// PROCESS DOCUMENT
// ---------------------------------------------------------

async function processDocument() {

    uploadError.classList.add("hidden");

    uploadError.textContent = "";


    const file =
        fileInput.files[0];


    if (!file) {

        uploadError.textContent =
            "Please select a document first.";

        uploadError.classList.remove("hidden");

        return;
    }


    processButton.disabled = true;

    processButton.textContent =
        "Processing...";


    const formData =
        new FormData();


    formData.append(
        "file",
        file
    );


    formData.append(
        "document_type",
        documentType.value
    );


    try {

        const response =
            await fetch(
                `${API_BASE}/documents/process`,
                {
                    method: "POST",
                    body: formData
                }
            );


        const data =
            await response.json();


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
            error.message ||
            "Something went wrong.";

        uploadError.classList.remove("hidden");


    } finally {

        processButton.disabled = false;

        processButton.textContent =
            "Process Document";

    }

}


// ---------------------------------------------------------
// LOAD HISTORY
// ---------------------------------------------------------

async function loadHistory() {

    try {

        const response =
            await fetch(
                `${API_BASE}/documents`
            );


        if (!response.ok) {

            throw new Error(
                `History API returned ${response.status}`
            );

        }


        const data =
            await response.json();


        historyBody.innerHTML = "";


        const documents =
            data.documents || [];


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

            const row =
                window.document.createElement("tr");


            row.style.cursor =
                "pointer";


            const statusClass =
                item.processing_status === "PASS"
                    ? "status-pass"
                    : "status-fail";


            const processedTime =
                item.processed_at
                    ? new Date(
                        item.processed_at
                    ).toLocaleString()
                    : "-";


            row.innerHTML = `
                <td>
                    ${escapeHtml(
                        item.document_name || "-"
                    )}
                </td>

                <td>
                    ${escapeHtml(
                        item.document_type || "-"
                    )}
                </td>

                <td>
                    <span class="status-badge ${statusClass}">
                        ${escapeHtml(
                            item.processing_status || "-"
                        )}
                    </span>
                </td>

                <td>
                    ${escapeHtml(
                        item.page_count ?? "-"
                    )}
                </td>

                <td>
                    ${escapeHtml(
                        processedTime
                    )}
                </td>
            `;


            row.addEventListener(
                "click",
                () => {
                    loadSavedDocument(
                        item.document_name
                    );
                }
            );


            historyBody.appendChild(row);

        });


    } catch (error) {

        console.error(
            "History loading error:",
            error
        );


        historyBody.innerHTML = `
            <tr>
                <td colspan="5">
                    Could not load processing history.
                </td>
            </tr>
        `;

    }

}


// ---------------------------------------------------------
// LOAD SAVED DOCUMENT
// ---------------------------------------------------------

async function loadSavedDocument(documentName) {

    try {

        const response =
            await fetch(
                `${API_BASE}/documents/${encodeURIComponent(
                    documentName
                )}`
            );


        if (!response.ok) {

            throw new Error(
                "Could not retrieve saved document."
            );

        }


        const result =
            await response.json();


        renderResult(result);


        resultSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });


    } catch (error) {

        uploadError.textContent =
            error.message ||
            "Could not load saved document.";

        uploadError.classList.remove(
            "hidden"
        );

    }

}


// ---------------------------------------------------------
// RAW JSON TOGGLE
// ---------------------------------------------------------

toggleJsonButton.addEventListener(
    "click",
    () => {

        const hidden =
            rawJson.classList.toggle(
                "hidden"
            );


        toggleJsonButton.textContent =
            hidden
                ? "Show JSON"
                : "Hide JSON";

    }
);


// ---------------------------------------------------------
// BUTTON EVENTS
// ---------------------------------------------------------

processButton.addEventListener(
    "click",
    processDocument
);


refreshHistoryButton.addEventListener(
    "click",
    loadHistory
);


// ---------------------------------------------------------
// INITIAL LOAD
// ---------------------------------------------------------

checkApiHealth();

loadHistory();


// ---------------------------------------------------------
// SHOW SELECTED FILE
// ---------------------------------------------------------

if (fileInput) {

    fileInput.addEventListener(
        "change",
        function () {

            const file =
                this.files[0];


            if (!file) {

                selectedFileName.textContent =
                    "Choose a document";

                selectedFileType.textContent =
                    "PDF, JPG or PNG";

                return;
            }


            selectedFileName.textContent =
                file.name;


            selectedFileType.textContent =
                `${(
                    file.size / 1024 / 1024
                ).toFixed(2)} MB · Ready to process`;

        }
    );

}