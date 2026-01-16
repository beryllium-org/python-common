#Maintainer: Panda <panda@bredos.org>

pkgname=python-bredos-common
pkgver=1.10.0
pkgrel=2
depends=('python>=3.12' 'python-pyrunning' 'python-pysetting' 'pyalpm' 'python-qrcode')
url="https://github.com/BredOS/python-common"
license=('GPLv3')
arch=('any')
makedepends=('python-setuptools' 'python-pipenv')
pkgdesc="Common python functions used in BredOS applications"

build() {
    cd $srcdir/..
    python setup.py build
}

package() {
    install -Dm644 $srcdir/../LICENSE $pkgdir/usr/share/licenses/$pkgname/LICENSE
    cd $srcdir/..
    python setup.py install --root=$pkgdir --optimize=1 --skip-build
}
