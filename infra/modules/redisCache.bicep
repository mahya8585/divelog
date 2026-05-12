/*
  Azure Cache for Redis モジュール（Basic C0）
  - 用途: flask-limiter の共有ストレージ（複数レプリカでレート制限状態を共有）
  - Basic SKU は VNet 注入非対応のため、TLS のみ・publicNetworkAccess:'Enabled' で公開。
  - Azure ポリシー（アクセスキー認証禁止）に合わせ、Entra ID (AAD) 認証のみ許可。
    - `disableAccessKeyAuthentication: true` でキー認証を完全に無効化
    - `redisConfiguration['aad-enabled']: 'true'` で AAD 認証を有効化
    - Container Apps の UAMI に対する Data アクセスポリシー割り当ては
      `redisAccessPolicy.bicep` モジュール側で行う（UAMI と循環依存にしないため）。
  - 最小 SKU/サイズで $約 $16/月 程度を見込む。
*/

param name     string
param location string

resource redis 'Microsoft.Cache/redis@2024-03-01' = {
  name    : name
  location: location
  properties: {
    sku: {
      name    : 'Basic'
      family  : 'C'
      capacity: 0
    }
    enableNonSslPort                 : false
    minimumTlsVersion                : '1.2'
    publicNetworkAccess              : 'Enabled'
    disableAccessKeyAuthentication   : true
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
      'aad-enabled'     : 'true'
    }
  }
}

output hostName string = redis.properties.hostName
output sslPort  int    = redis.properties.sslPort
output name     string = redis.name
output resourceId string = redis.id

