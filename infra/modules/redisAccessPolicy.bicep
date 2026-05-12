/*
  Azure Cache for Redis アクセスポリシー割り当て
  - アクセスキー認証を無効化した Redis に対し、Entra ID (AAD) 経由で
    特定のプリンシパル（UAMI 等）にデータ操作権限を付与する。
  - flask-limiter は INCR / EVAL / EXPIRE を使うため、ビルトインの
    `Data Contributor` アクセスポリシーで十分（FLUSH 等の管理操作は不要）。
  - UAMI と redisCache は別モジュールで作成されるため、循環依存を避けるべく
    この割り当てだけを独立した小さなモジュールに切り出している。
*/

@description('Azure Cache for Redis のリソース名')
param redisName string

@description('権限を付与するプリンシパル ID（UAMI の principalId / Entra User の objectId）')
param principalId string

@description('Redis 内での表示用エイリアス（管理用ラベル）')
param principalAlias string

@description('ビルトインアクセスポリシー名')
@allowed([
  'Data Owner'
  'Data Contributor'
  'Data Reader'
])
param accessPolicyName string = 'Data Contributor'

resource redis 'Microsoft.Cache/redis@2024-03-01' existing = {
  name: redisName
}

resource assignment 'Microsoft.Cache/redis/accessPolicyAssignments@2024-03-01' = {
  parent: redis
  name  : guid(redis.id, principalId, accessPolicyName)
  properties: {
    accessPolicyName: accessPolicyName
    objectId        : principalId
    objectIdAlias   : principalAlias
  }
}
