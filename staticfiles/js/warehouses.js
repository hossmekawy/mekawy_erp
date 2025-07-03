// Warehouses JavaScript Functions

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-refresh dashboard every 5 minutes
    if (window.location.pathname.includes('/warehouses/')) {
        setInterval(function() {
            if (document.querySelector('.warehouse-dashboard')) {
                location.reload();
            }
        }, 300000); // 5 minutes
    }

    // Search functionality
    initializeSearch();

    // Barcode scanner
    initializeBarcodeScanner();

    // Stock alerts
    checkStockAlerts();

    // Form validations
    initializeFormValidations();
});

// Search functionality
function initializeSearch() {
    const searchInputs = document.querySelectorAll('input[name="search"]');

    searchInputs.forEach(function(input) {
        let timeout;
        input.addEventListener('input', function() {
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                if (input.value.length >= 3 || input.value.length === 0) {
                    input.closest('form').submit();
                }
            }, 500);
        });
    });
}

// Barcode scanner functionality
function initializeBarcodeScanner() {
    const barcodeInput = document.getElementById('barcode-input');
    if (barcodeInput) {
        barcodeInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                searchByBarcode(this.value);
            }
        });
    }
}

function searchByBarcode(barcode) {
    if (!barcode) return;

    fetch(`/warehouses/api/product/barcode/${barcode}/`)
        .then(response => response.json())
        .then(data => {
            if (data.product) {
                fillProductForm(data.product);
            } else {
                showAlert('المنتج غير موجود', 'warning');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('حدث خطأ في البحث', 'danger');
        });
}

function fillProductForm(product) {
    const form = document.querySelector('form');
    if (form) {
        const productSelect = form.querySelector('select[name="product"]');
        if (productSelect) {
            // Add option if not exists
            let option = productSelect.querySelector(`option[value="${product.id}"]`);
            if (!option) {
                option = new Option(product.name, product.id);
                productSelect.add(option);
            }
            productSelect.value = product.id;
        }

        // Fill other fields if they exist
        const fields = ['name', 'code', 'cost_price', 'selling_price'];
        fields.forEach(field => {
            const input = form.querySelector(`input[name="${field}"]`);
            if (input && product[field]) {
                input.value = product[field];
            }
        });
    }
}

// Stock alerts
function checkStockAlerts() {
    const stockItems = document.querySelectorAll('.stock-item');
    let lowStockCount = 0;
    let outOfStockCount = 0;

    stockItems.forEach(function(item) {
        const quantity = parseInt(item.dataset.quantity || 0);
        const minLevel = parseInt(item.dataset.minLevel || 0);

        if (quantity === 0) {
            outOfStockCount++;
            item.classList.add('table-danger');
        } else if (quantity <= minLevel) {
            lowStockCount++;
            item.classList.add('table-warning');
        }
    });

    // Update alert counters
    updateAlertCounter('low-stock-count', lowStockCount);
    updateAlertCounter('out-of-stock-count', outOfStockCount);
}

function updateAlertCounter(elementId, count) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = count;
        if (count > 0) {
            element.classList.add('badge', 'bg-danger');
        }
    }
}

// Form validations
function initializeFormValidations() {
    const forms = document.querySelectorAll('form[novalidate]');

    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Custom validations
    validateStockTransfer();
    validatePrices();
}

function validateStockTransfer() {
    const transferForm = document.querySelector('#stock-transfer-form');
    if (!transferForm) return;

    const fromWarehouse = transferForm.querySelector('select[name="from_warehouse"]');
    const toWarehouse = transferForm.querySelector('select[name="to_warehouse"]');
    const quantityInput = transferForm.querySelector('input[name="quantity"]');

    if (fromWarehouse && toWarehouse) {
        [fromWarehouse, toWarehouse].forEach(select => {
            select.addEventListener('change', function() {
                if (fromWarehouse.value && toWarehouse.value && fromWarehouse.value === toWarehouse.value) {
                    toWarehouse.setCustomValidity('لا يمكن التحويل من نفس المخزن إلى نفسه');
                } else {
                    toWarehouse.setCustomValidity('');
                }
            });
        });
    }

    if (quantityInput) {
        quantityInput.addEventListener('input', function() {
            const quantity = parseFloat(this.value);
            const availableQuantity = parseFloat(this.dataset.available || 0);

            if (quantity > availableQuantity) {
                this.setCustomValidity(`الكمية المتاحة هي ${availableQuantity} فقط`);
            } else {
                this.setCustomValidity('');
            }
        });
    }
}

function validatePrices() {
    const costPriceInput = document.querySelector('input[name="cost_price"]');
    const sellingPriceInput = document.querySelector('input[name="selling_price"]');

    if (costPriceInput && sellingPriceInput) {
        function validatePriceRelation() {
            const costPrice = parseFloat(costPriceInput.value || 0);
            const sellingPrice = parseFloat(sellingPriceInput.value || 0);

            if (sellingPrice > 0 && costPrice > 0 && sellingPrice < costPrice) {
                sellingPriceInput.setCustomValidity('سعر البيع أقل من سعر التكلفة');
                showAlert('تحذير: سعر البيع أقل من سعر التكلفة', 'warning');
            } else {
                sellingPriceInput.setCustomValidity('');
            }
        }

        costPriceInput.addEventListener('input', validatePriceRelation);
        sellingPriceInput.addEventListener('input', validatePriceRelation);
    }
}

// Utility functions
function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container') || document.body;
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    alertContainer.insertBefore(alertDiv, alertContainer.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(function() {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('ar-EG', {
        style: 'currency',
        currency: 'EGP'
    }).format(amount);
}

function formatNumber(number) {
    return new Intl.NumberFormat('ar-EG').format(number);
}

// Export functions for use in other scripts
window.WarehouseUtils = {
    showAlert,
    formatCurrency,
    formatNumber,
    searchByBarcode
};

// AJAX helpers
function makeAjaxRequest(url, options = {}) {
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    };

    return fetch(url, {...defaultOptions, ...options })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        });
}

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]') ? .value || '';
}

// Real-time updates using WebSocket (if available)
function initializeWebSocket() {
    if (typeof WebSocket !== 'undefined') {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/warehouses/`;

        try {
            const socket = new WebSocket(wsUrl);

            socket.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            };

            socket.onclose = function() {
                console.log('WebSocket connection closed');
                // Attempt to reconnect after 5 seconds
                setTimeout(initializeWebSocket, 5000);
            };

        } catch (error) {
            console.log('WebSocket not available:', error);
        }
    }
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'stock_update':
            updateStockDisplay(data.stock_item);
            break;
        case 'low_stock_alert':
            showAlert(`تنبيه: مخزون منخفض للمنتج ${data.product_name}`, 'warning');
            break;
        case 'transfer_approved':
            showAlert(`تم الموافقة على التحويل رقم ${data.transfer_number}`, 'success');
            break;
    }
}

function updateStockDisplay(stockItem) {
    const stockRow = document.querySelector(`[data-stock-id="${stockItem.id}"]`);
    if (stockRow) {
        const quantityCell = stockRow.querySelector('.quantity-cell');
        if (quantityCell) {
            quantityCell.textContent = stockItem.quantity;

            // Update status badge
            const statusBadge = stockRow.querySelector('.status-badge');
            if (statusBadge) {
                if (stockItem.quantity <= stockItem.min_level) {
                    statusBadge.className = 'badge bg-danger';
                    statusBadge.textContent = 'منخفض';
                } else {
                    statusBadge.className = 'badge bg-success';
                    statusBadge.textContent = 'جيد';
                }
            }
        }
    }
}

// Initialize WebSocket if on warehouse pages
if (window.location.pathname.includes('/warehouses/')) {
    initializeWebSocket();
}