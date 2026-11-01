// Shop thử nghiệm: trang nào (trừ trang đăng nhập) cũng yêu cầu đăng nhập, chưa đăng nhập thì chuyển về login.html
(function () {
  var page = location.pathname.split('/').pop();
  if (page !== 'login.html' && !localStorage.getItem('shop_user')) {
    location.replace('login.html');
  }
})();

// Ô tìm kiếm ở đầu mọi trang
document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('search-btn');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var q = document.getElementById('q').value.trim();
    var out = document.getElementById('search-result');
    out.textContent = q ? 'Tìm thấy 2 kết quả cho "' + q + '"' : 'Vui lòng nhập từ khóa';
    out.style.display = 'block';
  });
});
