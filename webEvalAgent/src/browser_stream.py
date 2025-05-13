#!/usr/bin/env python3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from webEvalAgent.src.log_server import send_log
import logging
import time
import threading
import subprocess
import os
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory storage for latest screenshots and timestamps
latest_screenshots = {}
last_update_time = {}  # Store the last time each agent sent an update
active_instances = {}  # Track browser instances with their process IDs

class ScreenshotUpdate(BaseModel):
    agent_id: str
    screenshot: str # base64 encoded

@app.post("/update_screenshot")
async def update_screenshot(update: ScreenshotUpdate):
    """Receives screenshot updates from agents."""
    latest_screenshots[update.agent_id] = update.screenshot
    last_update_time[update.agent_id] = time.time()
    active_instances[update.agent_id] = True
    send_log(f"Received screenshot for {update.agent_id}", "📸", log_type='status')
    return {"status": "success"}

@app.get("/get_screenshots")
async def get_screenshots():
    """Provides the latest screenshots to the frontend."""
    # Clean up stale screenshots (older than 30 seconds)
    current_time = time.time()
    stale_agents = []
    
    for agent_id, last_time in list(last_update_time.items()):
        if current_time - last_time > 30:  # 30 seconds timeout
            stale_agents.append(agent_id)
            
    # Remove stale agents
    for agent_id in stale_agents:
        if agent_id in latest_screenshots:
            del latest_screenshots[agent_id]
        if agent_id in last_update_time:
            del last_update_time[agent_id]
        if agent_id in active_instances:
            del active_instances[agent_id]
            send_log(f"Removed stale agent: {agent_id}", "🗑️", log_type='status')
    
    return {
        "screenshots": latest_screenshots,
        "lastUpdate": last_update_time
    }

@app.post("/cleanup")
async def cleanup_browsers():
    """Force cleanup of browser processes."""
    try:
        if os.name == 'posix':  # Linux/Mac
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True)
        elif os.name == 'nt':  # Windows
            subprocess.run(["taskkill", "/f", "/im", "chrome.exe"], capture_output=True)
            subprocess.run(["taskkill", "/f", "/im", "chromium.exe"], capture_output=True)
        
        # Clear tracking data
        latest_screenshots.clear()
        last_update_time.clear()
        active_instances.clear()
        
        send_log("Cleaned up all browser processes", "🧹", log_type='status')
        return {"status": "success", "message": "All browser processes cleaned up"}
    except Exception as e:
        send_log(f"Error during cleanup: {e}", "❌", log_type='status')
        return {"status": "error", "message": str(e)}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serves the main HTML page to display agent views."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Operative WebEvalAgent Parallel Testing Mode</title>
        <style>
            body { font-family: sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
            h1 { text-align: center; color: #333; margin-bottom: 20px; }
            .control-panel { 
                text-align: center; 
                margin-bottom: 20px; 
                padding: 10px; 
                background: #fff; 
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .control-panel button {
                padding: 8px 16px;
                background: #0073e6;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin: 0 5px;
            }
            .control-panel button:hover {
                background: #0058b3;
            }
            .agents-container { display: flex; flex-wrap: wrap; justify-content: center; }
            .agent-view {
                border: 1px solid #ddd;
                margin: 10px;
                padding: 15px;
                width: 30%;
                min-width: 300px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                background-color: white;
                border-radius: 8px;
                position: relative;
             }
            .agent-view img {
                max-width: 100%;
                height: auto;
                border: 1px solid #eee;
                display: block;
                margin: 0 auto;
            }
            .agent-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                padding-bottom: 10px;
                border-bottom: 1px solid #eee;
            }
            .close-button {
                position: absolute;
                top: 5px;
                right: 5px;
                background: #ff4d4d;
                color: white;
                border: none;
                border-radius: 50%;
                width: 24px;
                height: 24px;
                line-height: 24px;
                text-align: center;
                font-weight: bold;
                cursor: pointer;
                z-index: 10;
            }
            .close-button:hover {
                background: #cc0000;
            }
            h3 { margin: 0; color: #444; }
            .timestamp { color: #888; font-size: 0.8em; }
            .metadata { margin-top: 10px; font-size: 0.9em; color: #555; }
            .status { font-weight: bold; }
            .status-active { color: green; }
            .status-stale { color: orange; }
        </style>
    </head>
    <body>
        <h1>Operative WebEvalAgent Parallel Testing Mode</h1>
        
        <div class="control-panel">
            <button id="cleanup-button">Clean Up All Browsers</button>
            <button id="refresh-button">Refresh Display</button>
            <span id="status-indicator" style="margin-left: 10px; font-style: italic;"></span>
        </div>
        
        <div id="agents-container" class="agents-container">
             <!-- Agent views will be dynamically added here -->
        </div>

        <script>
            const agentsContainer = document.getElementById('agents-container');
            const cleanupButton = document.getElementById('cleanup-button');
            const refreshButton = document.getElementById('refresh-button');
            const statusIndicator = document.getElementById('status-indicator');
            const knownAgentIds = new Set(); // Track agents with created divs
            const lastUpdated = {}; // Track when each agent was last updated
            
            // Setup button handlers
            cleanupButton.addEventListener('click', async () => {
                statusIndicator.textContent = "Cleaning up browsers...";
                try {
                    const response = await fetch('/cleanup', { method: 'POST' });
                    const result = await response.json();
                    statusIndicator.textContent = result.message;
                    setTimeout(() => { location.reload(); }, 2000); // Reload page after cleanup
                } catch (error) {
                    statusIndicator.textContent = "Error during cleanup: " + error;
                }
            });
            
            refreshButton.addEventListener('click', () => {
                location.reload();
            });

            function createOrUpdateAgentElement(agentId, screenshotBase64, metadata) {
                const now = new Date();
                lastUpdated[agentId] = now;
                
                let agentDiv = document.getElementById(`agent-${agentId}`);
                if (!agentDiv) {
                    // Create new div if it doesn't exist
                    knownAgentIds.add(agentId);
                    agentDiv = document.createElement('div');
                    agentDiv.className = 'agent-view';
                    agentDiv.id = `agent-${agentId}`;
                    
                    // Add close button
                    const closeButton = document.createElement('button');
                    closeButton.className = 'close-button';
                    closeButton.textContent = 'X';
                    closeButton.addEventListener('click', async () => {
                        // Remove from UI
                        agentDiv.remove();
                        knownAgentIds.delete(agentId);
                        
                        // Remove from tracking variables
                        delete lastUpdated[agentId];
                        
                        // Notify server
                        try {
                            await fetch('/cleanup', { method: 'POST' });
                        } catch (e) {
                            console.error("Error during cleanup:", e);
                        }
                    });
                    
                    const headerDiv = document.createElement('div');
                    headerDiv.className = 'agent-header';
                    
                    const title = document.createElement('h3');
                    title.textContent = metadata.description || `Agent: ${agentId}`;
                    
                    const timestamp = document.createElement('span');
                    timestamp.className = 'timestamp';
                    timestamp.id = `timestamp-${agentId}`;
                    timestamp.textContent = 'Just now';
                    
                    headerDiv.appendChild(title);
                    headerDiv.appendChild(timestamp);
                    
                    const img = document.createElement('img');
                    img.alt = `View for ${agentId}`;
                    
                    const metadataDiv = document.createElement('div');
                    metadataDiv.className = 'metadata';
                    metadataDiv.id = `metadata-${agentId}`;
                    metadataDiv.innerHTML = `
                        <div>Status: <span id="status-${agentId}" class="status status-active">Active</span></div>
                        <div>ID: ${agentId}</div>
                        <div>URL: ${metadata.url || 'N/A'}</div>
                    `;
                    
                    agentDiv.appendChild(closeButton);
                    agentDiv.appendChild(headerDiv);
                    agentDiv.appendChild(img);
                    agentDiv.appendChild(metadataDiv);
                    
                    agentsContainer.appendChild(agentDiv);
                    console.log(`Created view for ${agentId}`);
                }

                // Update the image source
                const imgElement = agentDiv.querySelector('img');
                if (imgElement) {
                    imgElement.src = `data:image/png;base64,${screenshotBase64}`;
                }
                
                // Update timestamp
                const timestampElement = document.getElementById(`timestamp-${agentId}`);
                if (timestampElement) {
                    timestampElement.textContent = 'Just now';
                }
                
                // Update status
                const statusElement = document.getElementById(`status-${agentId}`);
                if (statusElement) {
                    statusElement.textContent = 'Active';
                    statusElement.className = 'status status-active';
                }
            }
            
            function updateTimestamps() {
                const now = new Date();
                for (const agentId in lastUpdated) {
                    const timestamp = document.getElementById(`timestamp-${agentId}`);
                    const statusElement = document.getElementById(`status-${agentId}`);
                    
                    if (timestamp) {
                        const seconds = Math.floor((now - lastUpdated[agentId]) / 1000);
                        if (seconds < 60) {
                            timestamp.textContent = `${seconds}s ago`;
                        } else if (seconds < 3600) {
                            timestamp.textContent = `${Math.floor(seconds / 60)}m ago`;
                        } else {
                            timestamp.textContent = `${Math.floor(seconds / 3600)}h ago`;
                        }
                        
                        // Update status based on time since last update
                        if (statusElement) {
                            if (seconds > 10) {
                                statusElement.textContent = 'Stale';
                                statusElement.className = 'status status-stale';
                            }
                        }
                        
                        // Remove agents that haven't updated in more than 30 seconds
                        if (seconds > 30) {
                            const agentDiv = document.getElementById(`agent-${agentId}`);
                            if (agentDiv) {
                                agentDiv.remove();
                                knownAgentIds.delete(agentId);
                                delete lastUpdated[agentId];
                                console.log(`Removed stale agent: ${agentId}`);
                            }
                        }
                    }
                }
            }

            async function fetchAndUpdateScreenshots() {
                try {
                    const response = await fetch('/get_screenshots');
                    if (!response.ok) {
                        console.error(`Error fetching screenshots: ${response.status}`);
                        return;
                    }
                    const data = await response.json();
                    const screenshots = data.screenshots;
                    const lastUpdateTimes = data.lastUpdate;

                    // Update existing agent views and create new ones
                    for (const agentId in screenshots) {
                        const metadata = { 
                            description: agentId.includes('Instance') ? agentId : `Agent: ${agentId}`, 
                            status: 'Active', 
                            url: '' 
                        };
                        createOrUpdateAgentElement(agentId, screenshots[agentId], metadata);
                    }
                } catch (error) {
                    console.error("Error fetching screenshots:", error);
                }
            }

            // Fetch immediately and then every 1 second
            fetchAndUpdateScreenshots();
            setInterval(fetchAndUpdateScreenshots, 1000);
            setInterval(updateTimestamps, 1000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Function to periodically clean up stale instances
async def cleanup_stale_instances():
    while True:
        try:
            current_time = time.time()
            stale_agents = []
            
            for agent_id, last_time in list(last_update_time.items()):
                if current_time - last_time > 60:  # 60 seconds timeout for server cleanup
                    stale_agents.append(agent_id)
                    
            # Remove stale agents
            for agent_id in stale_agents:
                if agent_id in latest_screenshots:
                    del latest_screenshots[agent_id]
                if agent_id in last_update_time:
                    del last_update_time[agent_id]
                if agent_id in active_instances:
                    del active_instances[agent_id]
                    send_log(f"Server removed stale agent: {agent_id}", "🗑️", log_type='status')
        except Exception as e:
            send_log(f"Error during stale instance cleanup: {e}", "❌", log_type='status')
            
        await asyncio.sleep(30)  # Run cleanup every 30 seconds

# Start the cleanup task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_stale_instances())

if __name__ == "__main__":
    port = 8080
    send_log(f"Starting browser stream server on http://localhost:{port}", "🚀", log_type='status')
    uvicorn.run(app, host="0.0.0.0", port=port) 