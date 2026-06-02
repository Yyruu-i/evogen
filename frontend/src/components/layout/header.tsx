import { useLocation } from 'react-router-dom';

const breadcrumbs: Record<string, string> = {
  '/chat': '对话',
  '/memory': '记忆浏览器',
  '/memory/list': '记忆列表',
  '/memory/search': '记忆搜索',
  '/experience': '经验面板',
  '/experience/list': '经验记录',
  '/experience/feedback': '待反馈',
  '/persona': '人格配置',
  '/persona/attributes': '属性编辑',
  '/persona/preferences': '偏好管理',
  '/persona/sync': '同步状态',
  '/skills': '技能管理',
  '/skills/local': '本地技能',
  '/skills/hub': '技能市场',
  '/settings': '设置',
  '/settings/models': '模型配置',
  '/settings/platforms': '平台管理',
  '/settings/system': '系统状态',
};

export function Header() {
  const { pathname } = useLocation();

  const segments = pathname.split('/').filter(Boolean);
  let label = '对话';
  for (let i = segments.length; i > 0; i--) {
    const key = '/' + segments.slice(0, i).join('/');
    if (breadcrumbs[key]) {
      label = breadcrumbs[key];
      break;
    }
  }
  if (segments[0] === 'memory' && segments[1] && !breadcrumbs[pathname]) {
    label = '记忆详情';
  } else if (segments[0] === 'experience' && segments[1] && !breadcrumbs[pathname]) {
    label = '经验详情';
  }

  return (
    <header
      className="h-14 flex items-center px-8 flex-shrink-0"
      style={{
        background: 'var(--color-bg-glass)',
        backdropFilter: 'blur(24px) saturate(180%)',
        WebkitBackdropFilter: 'blur(24px) saturate(180%)',
        borderBottom: '1px solid var(--color-border-glass)',
      }}
    >
      <span className="text-[14px] font-medium text-secondary tracking-tight">{label}</span>
    </header>
  );
}
