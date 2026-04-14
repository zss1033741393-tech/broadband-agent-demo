import { useState, useEffect, KeyboardEvent } from 'react';
import { SendOutlined, BulbOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import styles from './InputBubble.module.css';

interface Props {
  disabled?: boolean;
  onSend: (content: string, deepThinking: boolean) => void;
  fillValue?: string;
  /** inline 模式：static 定位，嵌入父容器而不是绝对浮层 */
  inline?: boolean;
  /** 自定义 disabled 时的 placeholder */
  disabledPlaceholder?: string;
}

function InputBubble({ disabled, onSend, fillValue, inline, disabledPlaceholder }: Props) {
  const [value, setValue] = useState('');
  const [deepThinking, setDeepThinking] = useState(false);

  // 外部填入（编辑历史消息）时同步到输入框
  useEffect(() => {
    if (fillValue !== undefined && fillValue !== '') {
      setValue(fillValue);
    }
  }, [fillValue]);

  const canSend = value.trim().length > 0 && !disabled;

  const handleSend = () => {
    if (!canSend) return;
    onSend(value.trim(), deepThinking);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={inline ? styles.wrapperInline : styles.wrapper}>
      <div className={`${styles.bubble} ${disabled ? styles.disabled : ''}`}>
        <textarea
          className={styles.textarea}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? (disabledPlaceholder ?? 'Agent 处理中...') : '向 Agent 提问，回车发送，Shift+Enter 换行'}
          disabled={disabled}
          rows={2}
        />
        <div className={styles.toolbar}>
          <Tooltip title="深度思考（UI 演示，不影响后端）">
            <button
              type="button"
              className={`${styles.deepBtn} ${deepThinking ? styles.deepBtnActive : ''}`}
              onClick={() => setDeepThinking((v) => !v)}
              disabled={disabled}
            >
              <BulbOutlined />
              深度思考
            </button>
          </Tooltip>
          <button
            type="button"
            className={`${styles.sendBtn} ${canSend ? styles.sendBtnActive : ''}`}
            onClick={handleSend}
            disabled={!canSend}
            aria-label="发送"
          >
            <SendOutlined />
          </button>
        </div>
      </div>
    </div>
  );
}

export default InputBubble;
