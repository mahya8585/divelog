/*
  Azure Cache for Redis モジュール（Basic C0）
  - 用途: flask-limiter の共有ストレージ（複数レプリカでレート制限状態を共有）
  - Basic SKU は VNet 注入非対応のため、TLS のみ・publicNetworkAccess:'Enabled' + アクセスキー認証で接続。
    accessKey は main.bicep 側で Container App の secret に渡す。
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
    enableNonSslPort       : false
    minimumTlsVersion      : '1.2'
    publicNetworkAccess    : 'Enabled'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

output hostName string = redis.properties.hostName
output sslPort  int    = redis.properties.sslPort
output name     string = redis.name
output resourceId string = redis.id
