"""astrbot-plugin-mcsm-status
MCSManager 服务器状态查询 AstrBot 插件

功能:
  /mcsm status [名称]       -- 查看实例状态(概览/详情)
  /mcsm list                -- 列出所有实例
  /mcsm start [名称/序号]    -- 启动实例
  /mcsm stop [名称/序号]     -- 停止实例
  /mcsm restart [名称/序号]  -- 重启实例
  /mcsm kill [名称/序号]     -- 强制终止实例
  /mcsm cmd [实例名] <命令> -- 向服务器发送控制台命令
  /mcsm say <内容>          -- 向服务器发送 say 广播
  /mcsm panel [序号]         -- 状态面板（图片）
  /mcsm help                -- 显示帮助
"""

from .main import McsmStatusPlugin
