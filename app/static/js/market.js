// Market UI JavaScript
document.addEventListener('DOMContentLoaded', function() {
    let priceChart = null;

    // Initialize price history chart
    function initializePriceChart() {
        const ctx = document.getElementById('price-history-chart').getContext('2d');
        priceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Price History',
                    data: [],
                    borderColor: '#c4b5a0',
                    backgroundColor: 'rgba(196, 181, 160, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(88, 78, 66, 0.2)'
                        },
                        ticks: {
                            color: '#a39584'
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(88, 78, 66, 0.2)'
                        },
                        ticks: {
                            color: '#a39584'
                        }
                    }
                }
            }
        });
    }

    // Create a market row element
    function createMarketRow(item) {
        const row = document.createElement('div');
        row.className = 'market-row';
        
        const balance = item.buyOrders - item.sellOrders;
        const balancePercentage = Math.min(Math.abs(balance) / Math.max(item.buyOrders, item.sellOrders) * 100, 100);
        
        row.innerHTML = `
            <div class="col-icon">
                <img src="/static/images/items/${item.icon}" alt="${item.name}" width="24" height="24">
            </div>
            <div class="col-name">${item.name}</div>
            <div class="col-sell">${item.sellOrders.toLocaleString()}</div>
            <div class="col-buy">${item.buyOrders.toLocaleString()}</div>
            <div class="col-balance">
                <div class="balance-bar">
                    <div class="fill ${balance > 0 ? 'surplus' : 'deficit'}" 
                         style="width: ${balancePercentage}%"></div>
                </div>
            </div>
            <div class="col-price">£${item.price.toFixed(2)}</div>
            <div class="col-trend">
                <div class="trend-indicator ${item.trend > 0 ? 'positive' : 'negative'}">
                    ${item.trend > 0 ? '▲' : '▼'} ${Math.abs(item.trend)}%
                </div>
            </div>
        `;

        row.addEventListener('click', () => showItemDetails(item));
        return row;
    }

    // Update item details panel
    function showItemDetails(item) {
        document.getElementById('detail-item-name').textContent = item.name;
        document.getElementById('detail-price').textContent = item.price.toFixed(2);
        document.getElementById('detail-sell-orders').textContent = item.sellOrders.toLocaleString();
        document.getElementById('detail-buy-orders').textContent = item.buyOrders.toLocaleString();
        document.getElementById('detail-balance').textContent = (item.buyOrders - item.sellOrders).toLocaleString();

        // Update production sources
        const sourcesList = document.getElementById('production-sources');
        sourcesList.innerHTML = item.productionSources.map(source => 
            `<div class="detail-list-item">${source}</div>`
        ).join('');

        // Update price history chart
        updatePriceHistory(item.priceHistory);
    }

    // Update price history chart
    function updatePriceHistory(history) {
        if (!priceChart) {
            initializePriceChart();
        }

        priceChart.data.labels = history.dates;
        priceChart.data.datasets[0].data = history.prices;
        priceChart.update();
    }

    // Filter market items
    document.getElementById('market-filter').addEventListener('change', function(e) {
        const filter = e.target.value;
        fetchMarketData(filter);
    });

    // Fetch market data from the server
    async function fetchMarketData(filter = 'all') {
        try {
            const response = await fetch(`/api/market-data?filter=${filter}`);
            const data = await response.json();
            
            const tableBody = document.getElementById('market-items');
            tableBody.innerHTML = '';
            
            data.items.forEach(item => {
                tableBody.appendChild(createMarketRow(item));
            });

            // Show first item details by default
            if (data.items.length > 0) {
                showItemDetails(data.items[0]);
            }
        } catch (error) {
            console.error('Error fetching market data:', error);
        }
    }

    // Initial load
    initializePriceChart();
    fetchMarketData();
}); 