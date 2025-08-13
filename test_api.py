#!/usr/bin/env python3
"""API测试脚本."""

import asyncio
import json
import httpx
from typing import Dict, Any


class QwenProxyTester:
    """Qwen代理测试器."""
    
    def __init__(self, base_url: str = "http://localhost:8080", api_key: str = None):
        """初始化测试器."""
        self.base_url = base_url
        self.api_key = api_key
        
        # 设置默认headers
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)
    
    async def test_health(self) -> bool:
        """测试健康检查端点."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            success = response.status_code == 200
            print(f"✅ 健康检查: {'通过' if success else '失败'} (状态码: {response.status_code})")
            return success
        except Exception as e:
            print(f"❌ 健康检查失败: {e}")
            return False
    
    async def test_models(self) -> bool:
        """测试模型列表端点."""
        try:
            response = await self.client.get(f"{self.base_url}/v1/models")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                model_count = len(data.get('data', []))
                print(f"✅ 模型列表: 通过 (找到 {model_count} 个模型)")
                
                # 显示模型
                for model in data.get('data', []):
                    print(f"   - {model.get('id')}")
            else:
                print(f"❌ 模型列表失败: 状态码 {response.status_code}")
                print(f"   响应: {response.text}")
            
            return success
        except Exception as e:
            print(f"❌ 模型列表测试失败: {e}")
            return False
    
    async def test_chat_completion(self, use_streaming: bool = False) -> bool:
        """测试聊天完成端点."""
        try:
            payload = {
                "model": "qwen3-coder-plus",
                "messages": [
                    {"role": "user", "content": "你好，请简单介绍一下自己。"}
                ],
                "max_tokens": 100,
                "temperature": 0.7,
                "stream": use_streaming
            }
            
            mode_desc = "流式" if use_streaming else "常规"
            print(f"🔄 正在测试{mode_desc}聊天完成...")
            
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload
            )
            
            success = response.status_code == 200
            
            if success:
                if use_streaming:
                    print(f"✅ {mode_desc}聊天完成: 通过")
                    # 对于流式响应，只检查状态码
                    chunks = []
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            chunks.append(chunk)
                    print(f"   收到 {len(chunks)} 个数据块")
                else:
                    data = response.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    usage = data.get('usage', {})
                    
                    print(f"✅ {mode_desc}聊天完成: 通过")
                    print(f"   响应长度: {len(content)} 字符")
                    if usage:
                        print(f"   Token使用: {usage}")
                    
                    # 显示部分响应内容
                    if content:
                        preview = content[:100] + "..." if len(content) > 100 else content
                        print(f"   响应预览: {preview}")
            else:
                print(f"❌ {mode_desc}聊天完成失败: 状态码 {response.status_code}")
                print(f"   响应: {response.text}")
            
            return success
        except Exception as e:
            print(f"❌ {mode_desc}聊天完成测试失败: {e}")
            return False
    
    async def test_embeddings(self) -> bool:
        """测试嵌入向量端点."""
        try:
            payload = {
                "model": "text-embedding-v1",
                "input": "这是一个测试文本"
            }
            
            print("🔄 正在测试嵌入向量...")
            
            response = await self.client.post(
                f"{self.base_url}/v1/embeddings",
                json=payload
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                embedding_data = data.get('data', [])
                usage = data.get('usage', {})
                
                print("✅ 嵌入向量: 通过")
                if embedding_data:
                    vector_len = len(embedding_data[0].get('embedding', []))
                    print(f"   向量维度: {vector_len}")
                if usage:
                    print(f"   Token使用: {usage}")
            else:
                print(f"❌ 嵌入向量失败: 状态码 {response.status_code}")
                print(f"   响应: {response.text}")
            
            return success
        except Exception as e:
            print(f"❌ 嵌入向量测试失败: {e}")
            return False
    
    async def test_api_authentication(self) -> bool:
        """测试API Key认证."""
        try:
            print("🔄 正在测试API Key认证...")
            
            # 创建一个没有认证的客户端
            no_auth_client = httpx.AsyncClient(timeout=30.0)
            
            # 测试没有API Key的请求
            try:
                response = await no_auth_client.get(f"{self.base_url}/v1/models")
                if response.status_code == 401:
                    print("✅ 无API Key请求被正确拒绝")
                    no_auth_success = True
                else:
                    print(f"❌ 无API Key请求应该返回401，但返回了{response.status_code}")
                    no_auth_success = False
            except Exception as e:
                print(f"❌ 测试无认证请求失败: {e}")
                no_auth_success = False
            finally:
                await no_auth_client.aclose()
            
            # 测试错误的API Key
            wrong_key_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Authorization": "Bearer wrong-api-key"}
            )
            
            try:
                response = await wrong_key_client.get(f"{self.base_url}/v1/models")
                if response.status_code == 401:
                    print("✅ 错误API Key请求被正确拒绝")
                    wrong_key_success = True
                else:
                    print(f"❌ 错误API Key请求应该返回401，但返回了{response.status_code}")
                    wrong_key_success = False
            except Exception as e:
                print(f"❌ 测试错误API Key失败: {e}")
                wrong_key_success = False
            finally:
                await wrong_key_client.aclose()
            
            # 测试正确的API Key（如果提供了）
            if self.api_key:
                try:
                    response = await self.client.get(f"{self.base_url}/v1/models")
                    if response.status_code == 200:
                        print("✅ 正确API Key请求成功")
                        correct_key_success = True
                    else:
                        print(f"❌ 正确API Key请求失败，状态码: {response.status_code}")
                        correct_key_success = False
                except Exception as e:
                    print(f"❌ 测试正确API Key失败: {e}")
                    correct_key_success = False
            else:
                print("⚠️  未提供API Key，跳过正确API Key测试")
                correct_key_success = True  # 如果没有提供API Key，认为这部分测试通过
            
            return no_auth_success and wrong_key_success and correct_key_success
                
        except Exception as e:
            print(f"❌ API Key认证测试失败: {e}")
            return False
    
    async def test_auth_endpoints(self) -> bool:
        """测试认证端点（不实际执行认证）."""
        try:
            # 测试认证启动端点
            response = await self.client.post(f"{self.base_url}/auth/initiate")
            
            if response.status_code == 200:
                data = response.json()
                if 'verification_uri' in data and 'user_code' in data:
                    print("✅ 认证启动端点: 通过")
                    print(f"   验证URI: {data['verification_uri']}")
                    print(f"   用户代码: {data['user_code']}")
                    return True
                else:
                    print("❌ 认证启动端点: 响应格式不正确")
                    return False
            elif response.status_code == 401:
                print("✅ 认证启动端点: 正确要求API Key认证")
                return True
            else:
                print(f"❌ 认证启动端点失败: 状态码 {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 认证端点测试失败: {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """运行所有测试."""
        print("=" * 50)
        print("开始运行Qwen代理API测试")
        if self.api_key:
            print(f"使用API Key: {self.api_key[:8]}...")
        else:
            print("未提供API Key，将测试认证功能")
        print("=" * 50)
        
        results = {}
        
        # 健康检查（不需要认证）
        results['health'] = await self.test_health()
        
        # API Key认证测试
        results['api_auth'] = await self.test_api_authentication()
        
        # 模型列表
        results['models'] = await self.test_models()
        
        # 认证端点
        results['auth'] = await self.test_auth_endpoints()
        
        # 如果基本端点工作，尝试API端点
        if results['health'] and self.api_key:
            # 聊天完成（常规）
            results['chat_regular'] = await self.test_chat_completion(use_streaming=False)
            
            # 聊天完成（流式）
            results['chat_streaming'] = await self.test_chat_completion(use_streaming=True)
            
            # 嵌入向量
            results['embeddings'] = await self.test_embeddings()
        else:
            if not self.api_key:
                print("⚠️  跳过API测试，因为需要API Key")
            else:
                print("⚠️  跳过API测试，因为健康检查失败")
            results.update({
                'chat_regular': False,
                'chat_streaming': False,
                'embeddings': False
            })
        
        await self.client.aclose()
        
        # 总结结果
        print("\n" + "=" * 50)
        print("测试结果总结")
        print("=" * 50)
        
        passed = sum(results.values())
        total = len(results)
        
        for test_name, success in results.items():
            status = "✅ 通过" if success else "❌ 失败"
            print(f"{test_name:15}: {status}")
        
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("🎉 所有测试都通过了！")
        elif passed > 0:
            print("⚠️  部分测试失败，请检查服务器状态和认证配置")
        else:
            print("💥 所有测试都失败了，请检查服务器是否正在运行")
        
        return results


async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试Qwen代理API")
    parser.add_argument("--url", default="http://localhost:8080", help="代理服务器URL")
    parser.add_argument("--api-key", default="d8b94d28-7300-4fb0-bb61-7fd7248c3995", help="API Key用于认证")
    parser.add_argument("--test", choices=['health', 'models', 'chat', 'embeddings', 'auth', 'api_auth', 'all'], 
                       default='all', help="要运行的测试")
    
    args = parser.parse_args()
    
    tester = QwenProxyTester(args.url, args.api_key)
    
    try:
        if args.test == 'all':
            await tester.run_all_tests()
        elif args.test == 'health':
            await tester.test_health()
        elif args.test == 'models':
            await tester.test_models()
        elif args.test == 'chat':
            await tester.test_chat_completion()
        elif args.test == 'embeddings':
            await tester.test_embeddings()
        elif args.test == 'auth':
            await tester.test_auth_endpoints()
        elif args.test == 'api_auth':
            await tester.test_api_authentication()
    
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    finally:
        await tester.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())