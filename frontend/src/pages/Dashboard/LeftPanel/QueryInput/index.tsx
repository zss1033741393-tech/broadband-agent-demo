import { useState, KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { SendOutlined } from '@ant-design/icons';
import styles from './QueryInput.module.css';

function QueryInput() {
  const [value, setValue] = useState('');
  const navigate = useNavigate();

  const canSend = value.trim().length > 0;

  const handleSend = () => {
    if (!canSend) return;
    navigate('/workspace', {
      state: { prefillMessage: value.trim() },
    });
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.wrapper}>
      <div className={`${styles.bubble} ${value ? styles.active : ''}`}>
        <textarea
          className={styles.textarea}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，跳转 Agent 工作台..."
          rows={2}
        />
        <div className={styles.toolbar}>
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

export default QueryInput;
