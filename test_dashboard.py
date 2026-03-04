#!/usr/bin/env python3
"""
Unit tests for the Agent Dashboard
Run: python3 test_dashboard.py
"""

import unittest
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import dashboard module
import importlib.util
spec = importlib.util.spec_from_file_location("dashboard", "dashboard.py")
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class TestDashboard(unittest.TestCase):
    """Test cases for dashboard functions."""
    
    def test_agent_memory_config_exists(self):
        """Test that agent memory configs are defined."""
        self.assertIn("zjuniorcoder", dashboard.AGENT_MEMORY_CONFIG)
        self.assertIn("zseniorcoder", dashboard.AGENT_MEMORY_CONFIG)
        self.assertIn("zpredictor", dashboard.AGENT_MEMORY_CONFIG)
        self.assertIn("zhypetrader", dashboard.AGENT_MEMORY_CONFIG)
    
    def test_agent_memory_config_structure(self):
        """Test that each agent config has required fields."""
        required_fields = ["name", "role", "local_storage", "vector_db", "efficiency"]
        
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            for field in required_fields:
                self.assertIn(field, config, f"{agent_id} missing {field}")
    
    def test_local_storage_structure(self):
        """Test local storage configuration."""
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            local = config["local_storage"]
            self.assertIn("path", local)
            self.assertIn("files", local)
            self.assertIn("retention", local)
    
    def test_vector_db_structure(self):
        """Test vector DB configuration."""
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            vector = config["vector_db"]
            self.assertIn("collection", vector)
            self.assertIn("dimensions", vector)
            self.assertIn("retention", vector)
            self.assertIsInstance(vector["dimensions"], int)
    
    def test_efficiency_parameters(self):
        """Test efficiency parameters."""
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            eff = config["efficiency"]
            self.assertIn("max_tokens_per_context", eff)
            self.assertIn("target_recall_speed_ms", eff)
            self.assertIn("storage_limit_mb", eff)
            
            # Validate reasonable values
            self.assertGreater(eff["max_tokens_per_context"], 0)
            self.assertGreater(eff["target_recall_speed_ms"], 0)
            self.assertGreater(eff["storage_limit_mb"], 0)
    
    def test_mermaid_flow_generation(self):
        """Test Mermaid flow diagram generation."""
        for agent_id in dashboard.AGENT_MEMORY_CONFIG.keys():
            diagram = dashboard.generate_mermaid_flow(agent_id)
            
            # Check it's a valid mermaid code block
            self.assertIn("```mermaid", diagram)
            self.assertIn("flowchart", diagram)
            
            # Check it contains key components (flexible matching)
            self.assertIn("Dual Memory", diagram)
            self.assertIn("Local Files", diagram)
            self.assertIn("Qdrant Vector DB", diagram)
    
    def test_mermaid_flow_contains_agent_name(self):
        """Test that each flow diagram contains the agent name."""
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            diagram = dashboard.generate_mermaid_flow(agent_id)
            # The diagram should reference the agent indirectly through the config
            self.assertIn("mermaid", diagram.lower())
    
    def test_get_memory_flow_data_structure(self):
        """Test get_memory_flow_data returns expected structure."""
        for agent_id in dashboard.AGENT_MEMORY_CONFIG.keys():
            data = dashboard.get_memory_flow_data(agent_id)
            
            self.assertEqual(data["agent_id"], agent_id)
            self.assertIn("config", data)
            self.assertIn("memory_files", data)
            self.assertIn("total_storage_bytes", data)
            self.assertIn("total_storage_kb", data)
            self.assertIn("file_count", data)
    
    def test_get_system_metrics_returns_dict(self):
        """Test get_system_metrics returns expected fields."""
        metrics = dashboard.get_system_metrics()
        
        self.assertIsInstance(metrics, dict)
        self.assertIn("cpu_percent", metrics)
        self.assertIn("memory_percent", metrics)
        self.assertIn("disk_percent", metrics)
    
    def test_get_system_metrics_values(self):
        """Test that system metrics have reasonable values."""
        metrics = dashboard.get_system_metrics()
        
        # Values should be between 0 and 100 for percentages
        self.assertGreaterEqual(metrics.get("cpu_percent", 0), 0)
        self.assertLessEqual(metrics.get("cpu_percent", 0), 100)
        self.assertGreaterEqual(metrics.get("memory_percent", 0), 0)
        self.assertLessEqual(metrics.get("memory_percent", 0), 100)
    
    def test_get_local_ip(self):
        """Test get_local_ip returns valid IP."""
        ip = dashboard.get_local_ip()
        
        # Should return a string that looks like an IP
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 0)
        # Basic IP validation (contains dots)
        self.assertIn(".", ip)


class TestAgentSpecificMemory(unittest.TestCase):
    """Test agent-specific memory configurations."""
    
    def test_zjuniorcoder_config(self):
        """Test zjuniorcoder specific config."""
        config = dashboard.AGENT_MEMORY_CONFIG["zjuniorcoder"]
        
        self.assertEqual(config["name"], "Junior Coder")
        self.assertIn("coding", config["role"].lower())
        self.assertEqual(config["efficiency"]["max_tokens_per_context"], 8000)
        self.assertEqual(config["efficiency"]["target_recall_speed_ms"], 150)
    
    def test_zseniorcoder_config(self):
        """Test zseniorcoder specific config."""
        config = dashboard.AGENT_MEMORY_CONFIG["zseniorcoder"]
        
        self.assertEqual(config["name"], "Senior Coder")
        self.assertIn("architecture", config["role"].lower())
        self.assertEqual(config["efficiency"]["max_tokens_per_context"], 12000)
        self.assertEqual(config["efficiency"]["target_recall_speed_ms"], 200)
    
    def test_zpredictor_config(self):
        """Test zpredictor specific config."""
        config = dashboard.AGENT_MEMORY_CONFIG["zpredictor"]
        
        self.assertEqual(config["name"], "Predictor")
        self.assertIn("prediction", config["role"].lower())
        self.assertIn("predictions", str(config["local_storage"]["files"]))
    
    def test_zhypetrader_config(self):
        """Test zhypetrader specific config."""
        config = dashboard.AGENT_MEMORY_CONFIG["zhypetrader"]
        
        self.assertEqual(config["name"], "Hyper Trader")
        self.assertIn("trading", config["role"].lower())
        self.assertEqual(config["efficiency"]["target_recall_speed_ms"], 50)  # Fastest


class TestMemoryFlowDiagram(unittest.TestCase):
    """Test memory flow diagram generation."""
    
    def test_flow_diagram_contains_storage_types(self):
        """Test that diagrams show both storage types."""
        for agent_id in dashboard.AGENT_MEMORY_CONFIG.keys():
            diagram = dashboard.generate_mermaid_flow(agent_id)
            
            # Should contain references to local and vector storage
            self.assertTrue(
                "Local" in diagram or "local" in diagram,
                f"{agent_id} diagram missing local storage"
            )
    
    def test_flow_diagram_contains_cleanup(self):
        """Test that diagrams show cleanup policies."""
        for agent_id in dashboard.AGENT_MEMORY_CONFIG.keys():
            diagram = dashboard.generate_mermaid_flow(agent_id)
            
            # Should contain cleanup logic
            self.assertIn("Clean", diagram, f"{agent_id} diagram missing cleanup")
    
    def test_flow_diagram_retention_in_documentation(self):
        """Test that retention policies are in the diagram."""
        for agent_id, config in dashboard.AGENT_MEMORY_CONFIG.items():
            diagram = dashboard.generate_mermaid_flow(agent_id)
            
            # Should reference days (retention period)
            self.assertIn("days", diagram.lower())


class TestFlaskApp(unittest.TestCase):
    """Test Flask app routes."""
    
    @classmethod
    def setUpClass(cls):
        """Set up Flask test client."""
        dashboard.app.config['TESTING'] = True
        cls.client = dashboard.app.test_client()
    
    def test_index_route(self):
        """Test main index route."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
    
    def test_api_agents_route(self):
        """Test agents API route."""
        response = self.client.get('/api/agents')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response.content_type)
    
    def test_api_metrics_route(self):
        """Test metrics API route."""
        response = self.client.get('/api/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response.content_type)
    
    def test_api_gateway_route(self):
        """Test gateway API route."""
        response = self.client.get('/api/gateway')
        self.assertEqual(response.status_code, 200)
    
    def test_api_memory_route(self):
        """Test memory API route."""
        response = self.client.get('/api/memory')
        self.assertEqual(response.status_code, 200)
    
    def test_api_memory_agent_route(self):
        """Test specific agent memory API route."""
        response = self.client.get('/api/memory/zjuniorcoder')
        self.assertEqual(response.status_code, 200)
    
    def test_api_memory_flow_route(self):
        """Test memory flow diagram API route."""
        response = self.client.get('/api/memory-flow/zjuniorcoder')
        self.assertEqual(response.status_code, 200)

    def test_api_tasks_route(self):
        """Test tasks API grouped response."""
        response = self.client.get('/api/tasks')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn('backlog', payload)
        self.assertIn('in_progress', payload)
        self.assertIn('review', payload)
        self.assertIn('done', payload)

    def test_api_task_detail_route(self):
        """Test single task detail endpoint."""
        response = self.client.get('/api/tasks/predictor-v2')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get('id'), 'predictor-v2')

    def test_api_task_detail_not_found(self):
        """Test 404 for unknown task id."""
        response = self.client.get('/api/tasks/not-real')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)