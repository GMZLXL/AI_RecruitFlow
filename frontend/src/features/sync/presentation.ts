import type { SyncState } from '../../services/api';

export const SYNC_STATES: Record<SyncState, { label: string; color: string }> = {
  pending: { label: '待同步', color: 'default' },
  processing: { label: '处理中', color: 'processing' },
  mock_synced: { label: '模拟已同步', color: 'green' },
  synced: { label: '已同步', color: 'green' },
  failed: { label: '失败 · 等待重试', color: 'orange' },
  dead: { label: '死信 · 需人工处理', color: 'red' },
  superseded: { label: '已由新版本覆盖', color: 'default' },
};

export const syncErrorLabel = (code: string | null) => code ? ({
  REMOTE_TIMEOUT: '远端超时，业务记录已保留',
  REMOTE_PERMISSION_DENIED: '远端无权限，请恢复授权后重试',
  REMOTE_RECORD_MISSING: '远端记录不存在，请核对映射，系统不会自动新建',
  REMOTE_MAPPING_MISSING: '映射丢失，请核对远端记录并恢复映射',
  BLOCKED_BY_CREDENTIALS: '缺少腾讯文档 Token',
  BLOCKED_BY_SCHEMA: '腾讯文档工具 Schema 和字段映射尚未验证',
  INVALID_PROJECTION: '投影结构不兼容，请检查任务数据版本',
  CLAIM_EXPIRED: '任务领取连续过期，请检查处理器后重试',
  INTERNAL_SYNC_ERROR: '处理异常，请检查服务端状态后重试',
  LEGACY_SYNC_ERROR: '历史同步失败，请检查服务端状态后重试',
} as Record<string, string>)[code] ?? code : '—';
