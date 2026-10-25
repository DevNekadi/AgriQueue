/**
 * AgriQueue - Front-End Interactions & Queue Polling
 * Lightweight vanilla JavaScript designed for responsive, accessible interaction.
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Auto-dismiss flash alerts after 6 seconds
  const alerts = document.querySelectorAll(".alert-dismissible");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) {
        bsAlert.close();
      }
    }, 6000);
  });

  // 2. Real-Time Dynamic Queue Polling (on queue status page)
  const queueStatusContainer = document.getElementById("live-queue-tracker");
  if (queueStatusContainer) {
    const bookingId = queueStatusContainer.dataset.bookingId;
    if (bookingId) {
      initQueuePolling(bookingId);
    }
  }

  // 3. Table Live Filter for Operator & Admin Dashboards
  const tableSearchInput = document.getElementById("table-quick-search");
  if (tableSearchInput) {
    tableSearchInput.addEventListener("input", function (e) {
      const filter = e.target.value.toLowerCase().trim();
      const rows = document.querySelectorAll(".filter-target-table tbody tr");
      rows.forEach(function (row) {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? "" : "none";
      });
    });
  }

  // 4. Booking Form Dynamic Calculations (Estimated Total MSP Value)
  const cropSelect = document.getElementById("booking-crop-select");
  const quantityInput = document.getElementById("booking-quantity-input");
  const estValueDisplay = document.getElementById("estimated-msp-val");

  function updateMspPreview() {
    if (!cropSelect || !quantityInput || !estValueDisplay) return;
    const selectedOption = cropSelect.options[cropSelect.selectedIndex];
    const mspPrice = parseFloat(selectedOption?.dataset?.msp || 0);
    const qty = parseFloat(quantityInput.value || 0);
    if (mspPrice > 0 && qty > 0) {
      const total = (mspPrice * qty).toLocaleString("en-IN", {
        maximumFractionDigits: 2,
        style: "currency",
        currency: "INR"
      });
      estValueDisplay.textContent = total;
    } else {
      estValueDisplay.textContent = "₹ 0.00";
    }
  }

  if (cropSelect && quantityInput) {
    cropSelect.addEventListener("change", updateMspPreview);
    quantityInput.addEventListener("input", updateMspPreview);
  }
});

/**
 * Periodically poll the queue status API without overwhelming the server.
 * Interval: 12 seconds
 */
function initQueuePolling(bookingId) {
  let pollInterval = setInterval(fetchQueueUpdate, 12000);

  async function fetchQueueUpdate() {
    try {
      const response = await fetch(`/api/queue-status/${bookingId}`);
      if (!response.ok) return;
      const data = await response.json();
      if (!data.success) return;

      // Update position badge
      const posEl = document.getElementById("poll-queue-pos");
      if (posEl) posEl.textContent = `#${data.queue_position}`;

      // Update farmers ahead
      const aheadEl = document.getElementById("poll-farmers-ahead");
      if (aheadEl) aheadEl.textContent = `${data.farmers_ahead} farmer(s) ahead`;

      // Update predicted wait
      const waitEl = document.getElementById("poll-pred-wait");
      if (waitEl) waitEl.textContent = data.formatted_wait;

      // Update status pill
      const statusPill = document.getElementById("poll-status-pill");
      if (statusPill) {
        statusPill.textContent = data.status;
        statusPill.className = `status-pill ${data.status.toLowerCase()}`;
      }

      // If finished, stop polling
      if (["COMPLETED", "CANCELLED", "REJECTED"].includes(data.status)) {
        clearInterval(pollInterval);
      }
    } catch (err) {
      console.warn("Queue polling failed temporarily:", err);
    }
  }
}
